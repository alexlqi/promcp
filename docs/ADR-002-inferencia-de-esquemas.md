# ADR-002 · Inferencia de esquemas robusta ante anotaciones modernas

- **Autor:** Alejandro Andrade — [@alexlqi](https://github.com/alexlqi)
- **Estado:** Propuesto
- **Fecha:** 2026-08-17
- **Versión objetivo:** ninguna — el parche **no sube la versión**.
- **Nota:** propuesto para 0.3.1 y renumerado a 0.4.1, 0.5.1 y 0.5.2 según
  se iban publicando releases que ocupaban el número. Ya no se numera: la
  entrada de CHANGELOG va bajo `[Unreleased]` y el número lo pone quien corte
  la release. El defecto sigue vivo tras 0.4.0, 0.4.1, 0.5.0 y 0.5.1, y con él
  el workaround en `devmemomcp`.

## Contexto

`promcp/decorators.py::_infer_input_schema` construye el `inputSchema` de cada
tool a partir de las anotaciones de tipo de la función decorada. Ese esquema es
lo que consume `promcp.linter.checker` y lo que exportan los adapters.

La implementación actual compara `param.annotation` contra un diccionario de
tipos desnudos:

```python
PY_TO_JSON = {str: "string", int: "integer", ..., dict: "object"}
json_type  = PY_TO_JSON.get(inner)
```

Esa comparación por identidad solo acierta con anotaciones que sean exactamente
el tipo builtin. Cualquier forma moderna de anotar —que es la que se usa en
código nuevo— no está en el diccionario, no lanza error, y cae al `else` que
asigna `{}`.

El fallo se descubrió construyendo `devmemomcp`, el primer servidor real sobre
proMCP: el linter rechazaba un `can_do` correcto con un mensaje sobre
`semantic_tags`, un campo que la función no tenía por qué declarar.

## Hechos verificados

Medido contra `promcp` 0.5.1 con Python 3.12. La columna "actual" es lo que
produce hoy `_infer_input_schema`:

| Anotación | Actual (0.5.1) | Correcto | Clase de fallo |
|---|---|---|---|
| `str`, `int`, `dict`, `list` | `{"type": ...}` | igual | — ok |
| `Optional[str]` | `{"type": ["string","null"]}` | igual | — ok |
| **cualquiera bajo PEP 563** | `{}` | según tipo | **1 · anotaciones diferidas** |
| `list[str]`, `dict[str, Any]` | `{}` | `array` / `object` | **2 · genéricos PEP 585** |
| `List[str]`, `Dict[str, Any]` | `{}` | `array` / `object` | **3 · genéricos `typing`** |
| `str \| None` | `{}` | `["string","null"]` | **4 · uniones PEP 604** |
| `Optional[list[str]]` | `{}` | `["array","null"]` | **5 · composición de 1+2** |

Las cinco clases son el mismo defecto de fondo: **la inferencia solo entiende
tipos desnudos evaluados**, y ninguna de las formas anteriores lo es.

**La clase 1 es la grave**, porque es silenciosa y total. Basta que un módulo
declare `from __future__ import annotations` —recomendación estándar, y
comportamiento por defecto propuesto para el lenguaje— para que
`inspect.signature` devuelva las anotaciones como *strings* (`"dict"`,
`"Optional[list[str]]"`). Ninguna string está en `PY_TO_JSON`, así que **todos**
los parámetros de **todos** los tools de ese módulo quedan como `{}`:

```
CON future import:
   intent: {}   scope: {}   title: {}   n: {}   flag: {}
```

### El síntoma engaña

El daño no es solo un esquema pobre. El linter de proMCP interpreta el esquema
vacío como una violación de contrato distinta y emite un diagnóstico que apunta
al sitio equivocado:

```
ERROR can_do: I002 can_do intent must include 'semantic_tags' array.
```

`checker.check_input_schema` tiene una rama que acepta `intent` cuando llega
como `{"type": "object"}` sin propiedades —anotación `dict`, comentada en el
código como *"runtime-enforced"*—. Con el esquema vacío no hay `type`, esa rama
no entra, y se cae al `elif` que exige `semantic_tags`. El autor del servidor
recibe un error sobre un campo que nunca declaró, sin pista alguna de que la
causa real es un import en la cabecera del archivo.

Esto es peor que un fallo ruidoso: **la única forma de arreglarlo hoy es quitar
el `from __future__ import annotations`**, y llegar a esa conclusión requiere
leer el código de la librería. En `devmemomcp` está documentado como comentario
en los tres módulos de la superficie, que es exactamente la clase de deuda que
una librería no debería exportar a sus consumidores.

### Hallazgo colateral

El comentario de `checker.py` que justifica saltarse la validación —*"accept it,
semantic_tags is enforced at runtime by the decorator"*— **es falso**.
`can_do_tool` solo comprueba que exista un parámetro llamado `intent`; nunca
inspecciona `semantic_tags`, ni en decoración ni en la llamada. La regla I002 es
por tanto inaplicable en la práctica: o se valida de verdad, o se rebaja a
WARNING. Se documenta aquí y **se deja fuera de este parche** por no ser el mismo
defecto: I002 es una decisión de spec, no un bug de inferencia.

## Decisión

Reescribir `_infer_input_schema` sobre la **API de introspección de `typing`**
en lugar de comparaciones por identidad. Tres cambios de mecanismo:

1. **Resolver anotaciones diferidas** con `typing.get_type_hints(fn)`, que las
   evalúa contra los globals del módulo de la función. Envuelto en `try/except`
   con degradación a las anotaciones crudas: ante una anotación irresoluble se
   produce un esquema peor, **nunca una excepción en tiempo de decoración**.

2. **Consultar `typing.get_origin(ann)`** además del tipo desnudo. `get_origin`
   normaliza `list[str]`, `List[str]` y `Sequence`-likes a `list`, con lo que las
   clases de fallo 2 y 3 desaparecen con una sola línea.

3. **Detectar uniones por origin**, contra `(typing.Union, types.UnionType)`, en
   lugar de por presencia de `__origin__`. `types.UnionType` se resuelve con
   `getattr` para no romper en intérpretes anteriores a 3.10.

Como beneficio derivado, el esquema gana `items` en los arrays
(`list[str]` → `{"type":"array","items":{"type":"string"}}`), que es
precisamente lo que la regla I002 querría poder verificar.

### Cambio de comportamiento a decidir

Hoy un parámetro `Optional[X]` **sin valor por defecto** se excluye de
`required`. Es incorrecto: en Python ese argumento es obligatorio: acepta `None`
como valor, pero no acepta ausencia. Un modelo que lea el esquema omitirá un
parámetro que la función exige, y la llamada fallará con `TypeError`.

La corrección es tratar presencia y nulabilidad como cosas distintas: `required`
depende solo de si hay default. **Es el único cambio del ADR con radio de
impacto**, porque solo *añade* nombres a `required` y puede volver más estricta
la validación río abajo en servidores existentes. Se propone incluirlo en 0.3.1
por ser una corrección de exactitud, no una funcionalidad nueva; si se prefiere
conservadurismo, se difiere a 0.6.0 sin afectar al resto del parche.

## Alternativas consideradas

| Opción | Veredicto |
|---|---|
| Reescribir sobre `typing.get_type_hints` + `get_origin` | **Elegida.** Ataca las cinco clases con un solo mecanismo, sin dependencias nuevas y sin cambiar la firma pública. |
| Documentar "no uses `from __future__ import annotations`" | **Rechazada.** Exporta el defecto al consumidor, es invisible hasta que el linter miente, y colisiona con la dirección del lenguaje. |
| Delegar la inferencia en Pydantic | **Rechazada para 0.3.1.** Resolvería más casos, pero mete una dependencia pesada en el core por un defecto que se arregla con la stdlib. Reconsiderable si el esquema tiene que crecer a `enum`/`constr`. |
| Exigir `inputSchema` explícito en los decoradores | **Rechazada.** Rompe la API y el atractivo de la librería es precisamente inferirlo. Válida como *escotilla opcional* futura, no como sustituto. |
| Detectar y lanzar error ante esquema vacío | **Descartada como solución**, retenida como mejora: convertir el fallo silencioso en ruidoso ayuda, pero sigue sin producir el esquema correcto. |

## Validación

Parche aplicado sobre una copia de 0.3.0 y ejercitado contra dos suites:

| Suite | Resultado |
|---|---|
| `promcp/tests` (propia, sobre 0.5.1) | **50 passed** — sin regresiones |
| `devmemomcp/tests` (consumidor real) | **56 passed** |

Prueba de que el parche elimina el workaround — se restaura
`from __future__ import annotations` en los tres módulos de la superficie de
`devmemomcp` y se pasa el linter con cada versión:

```
--- proMCP 0.5.1 ---
    ERROR can_do: I002 can_do intent must include 'semantic_tags' array.
    => 1 errores
    can_do inputSchema: {"properties": {"intent": {}, "scope": {}}, ...}

--- con el parche ---
    => 0 errores
    can_do inputSchema: {"properties": {"intent": {"type": "object"},
       "scope": {"type": ["array","null"], "items": {"type": "string"}}}, ...}
```

### Tests de regresión a añadir

En `tests/test_decorators.py`, uno por clase de fallo — sin ellos el defecto
vuelve en cuanto alguien toque la función:

- `test_pep563_deferred_annotations` — módulo compilado con `from __future__ import annotations`; ningún parámetro anotado puede quedar en `{}`.
- `test_pep585_builtin_generics` — `list[str]` → `array` con `items`.
- `test_typing_generics` — `List[str]`, `Dict[str, Any]`.
- `test_pep604_unions` — `str | None` → `["string","null"]`.
- `test_optional_generic_composition` — `Optional[list[str]]`.
- `test_unresolvable_annotation_degrades` — anotación irresoluble → `{}`, sin excepción.
- `test_varargs_are_skipped` — `*args`/`**kwargs` no aparecen en `properties`.

## Consecuencias

- Los servidores proMCP pueden usar anotaciones modernas sin workarounds, y el
  comentario que hoy encabeza los tres módulos de superficie de `devmemomcp` se
  borra.
- Los `inputSchema` exportados mejoran para **todos** los servidores existentes
  sin que cambien una línea: los parámetros que hoy salen como `{}` pasan a
  llevar tipo. Los adapters y el linter se benefician sin cambios.
- La regla I002 sigue siendo inaplicable hasta que se decida validar
  `semantic_tags` de verdad o rebajarla a WARNING. **Queda abierta para 0.6.0.**
- `typing.get_type_hints` importa el módulo de la función; con anotaciones que
  referencian nombres solo disponibles bajo `TYPE_CHECKING` puede fallar. El
  `try/except` lo cubre degradando a `{}`, que es el comportamiento actual: el
  peor caso del parche es empatar con lo que ya hay.

## Entrada de CHANGELOG propuesta

```markdown
## [Unreleased]

### Fixed

- **`_infer_input_schema` ignoraba silenciosamente las anotaciones modernas.**
  Producía `inputSchema` vacío (`{}`) para: anotaciones diferidas por PEP 563
  (`from __future__ import annotations` — afectaba a TODOS los parámetros del
  módulo), genéricos builtin (`list[str]`, `dict[str, Any]`), genéricos de
  `typing` (`List[str]`), uniones PEP 604 (`str | None`) y sus composiciones
  (`Optional[list[str]]`). La inferencia ahora resuelve las anotaciones con
  `typing.get_type_hints` y normaliza los genéricos con `typing.get_origin`.
- **El esquema vacío se manifestaba como un diagnóstico engañoso.** Un `can_do`
  correcto declarado en un módulo con PEP 563 fallaba con
  `I002 can_do intent must include 'semantic_tags' array`, apuntando a un campo
  que el autor nunca declaró en lugar de a la causa real.
- **`required` ya no excluye los parámetros `Optional[X]` sin valor por
  defecto.** Nulabilidad y presencia son distintas: `Optional[str]` sin default
  es un argumento obligatorio que acepta `None`, y declararlo opcional inducía
  a omitirlo y provocar un `TypeError` en la llamada.

### Added

- Los arrays del `inputSchema` ahora declaran `items`
  (`list[str]` → `{"type": "array", "items": {"type": "string"}}`).
- `*args` / `**kwargs` se omiten de `properties` en lugar de emitirse sin tipo.

### Known issues

- La regla `I002` del linter es inaplicable: el comentario de `checker.py` dice
  que `semantic_tags` se valida en runtime, pero `can_do_tool` solo comprueba la
  existencia del parámetro `intent`. Pendiente de decidir en 0.6.0 si se valida
  de verdad o se rebaja a WARNING.
```

## Implementación

Parche completo en `promcp/decorators.py`, reemplazando `_infer_input_schema` y
añadiendo tres helpers privados. Requiere `import types` e `import typing` en la
cabecera del módulo.

```python
PY_TO_JSON: dict = {
    str: "string", int: "integer", float: "number",
    bool: "boolean", list: "array", dict: "object",
}

_UNION_ORIGINS: tuple = (Union, getattr(types, "UnionType", Union))


def _resolve_hints(fn: Callable) -> dict:
    """Resuelve anotaciones a objetos de tipo reales.

    Bajo PEP 563 `inspect.signature` devuelve las anotaciones como *strings*.
    `typing.get_type_hints` las evalúa contra los globals del módulo de la
    función. Si la evaluación falla (nombres locales, tipos solo disponibles
    bajo TYPE_CHECKING) se degrada a las anotaciones crudas: peor esquema,
    nunca una excepción en tiempo de decoración.
    """
    try:
        return typing.get_type_hints(fn)
    except Exception:
        return {}


def _unwrap_optional(ann):
    """`Optional[X]` / `X | None` → `(X, True)`. Otro caso → `(ann, False)`."""
    if typing.get_origin(ann) not in _UNION_ORIGINS:
        return ann, False
    args = typing.get_args(ann)
    non_null = [a for a in args if a is not type(None)]
    if len(non_null) != len(args):
        return (non_null[0] if len(non_null) == 1 else Any), True
    return ann, False


def _json_type(ann) -> Optional[str]:
    """Tipo JSON de una anotación, o None si no se puede determinar.

    Mira el tipo desnudo y después su `origin`, que es lo que convierte
    `list[str]`, `typing.List[str]` y `dict[str, Any]` en array/object.
    """
    if ann in PY_TO_JSON:
        return PY_TO_JSON[ann]
    origin = typing.get_origin(ann)
    if origin is not None and origin in PY_TO_JSON:
        return PY_TO_JSON[origin]
    return None


def _schema_for(ann) -> dict:
    json_type = _json_type(ann)
    if json_type is None:
        return {}
    schema = {"type": json_type}
    if json_type == "array":
        args = typing.get_args(ann)
        if len(args) == 1:
            item_type = _json_type(args[0])
            if item_type:
                schema["items"] = {"type": item_type}
    return schema


def _infer_input_schema(fn: Callable) -> dict:
    """
    Build a JSON Schema inputSchema from Python type annotations.

    Supports str, int, float, bool, list, dict, their parameterized generics
    (list[str], dict[str, Any], typing.List[str]), Optional[X], X | None, and
    PEP 563 deferred annotations. Falls back to {} for anything else.
    """
    sig = inspect.signature(fn)
    hints = _resolve_hints(fn)

    properties: dict = {}
    required: list = []

    for name, param in sig.parameters.items():
        if name == "self":
            continue
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue

        ann = hints.get(name, param.annotation)

        if ann is inspect.Parameter.empty:
            properties[name] = {}
            if param.default is inspect.Parameter.empty:
                required.append(name)
            continue

        inner, is_optional = _unwrap_optional(ann)
        schema = _schema_for(inner)
        if is_optional and "type" in schema:
            schema = {**schema, "type": [schema["type"], "null"]}
        properties[name] = schema

        # Presencia y nulabilidad son distintas: Optional[X] sin default sigue
        # siendo obligatorio. Ver "Cambio de comportamiento a decidir".
        if param.default is inspect.Parameter.empty:
            required.append(name)

    schema: dict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema
```
