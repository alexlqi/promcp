# ADR-001 · Incorporación de FastMCP en ProMCP

- **Autor:** Alejandro Andrade — [@alexlqi](https://github.com/alexlqi)
- **Estado:** Propuesto
- **Fecha:** 2026-07-22

## Contexto

FastMCP se invoca en prácticamente todo ProMCP. Surge la pregunta de
"incorporarlo al codebase" (vendorizar `@latest`) por comodidad. Hay que
separar la dimensión legal de la estratégica.

## Hechos verificados

- FastMCP está bajo **Apache-2.0** (declarado en PyPI y en el repo; SPDX
  `Apache-2.0`). Autor: Jeremiah Lowin. Proyecto ahora bajo PrefectHQ.
- Serie actual **3.4.x**. Releases recientes son mayormente hardening de
  seguridad (SSRF/OAuth en 3.4.3; floor de Starlette por CVE-2026-48710 en
  3.4.1). Upstream muy activo (~1M descargas/día).

## Decisión

Incorporar FastMCP como **dependencia de transporte de primera clase,
pinneada por rango y aislada tras `promcp.transport`** (patrón adapter,
contract-first). **NO** se vendoriza `@latest`.

## Alternativas consideradas

| Opción | Veredicto |
|---|---|
| Vendorizar `@latest` (copiar fuente al repo) | **Rechazada.** `@latest` se congela al copiarlo; heredas todo el backlog de CVEs de una lib que hoy es puro hardening. FastMCP es plomería, no tu moat. |
| Dependencia pinneada + adapter | **Elegida.** Resuelve "que venga incluido y pre-cableado" sin pasivo de seguridad; encaja con Harness Engineering (el moat es la capa FSM/contratos por encima). |
| Vendor pinneado auditado (versión fija + NOTICE + hash) | **Reservada** solo para despliegues air-gap / regulados (indaLoop, 21 CFR Part 11), y aun así sobre una versión *específica*, jamás `@latest`. |

## Obligaciones legales (Apache-2.0), si distribuyes ProMCP

1. Conservar `LICENSE` y aviso de copyright de FastMCP → `THIRD_PARTY_LICENSES/fastmcp.txt`.
2. Incluir el texto íntegro de Apache-2.0 y el `NOTICE` → archivo `NOTICE`.
3. Marcar como modificado cualquier archivo de FastMCP que llegaras a tocar (§4).
4. No usar las marcas "FastMCP"/"Prefect" para insinuar respaldo de ProMCP.

> Nota: uso puramente interno o SaaS (sin distribuir el binario/fuente al
> cliente) no dispara la mayoría de gatillos de "distribution" de Apache-2.0,
> pero mantener la atribución es buena práctica igual. Esto no es asesoría
> legal; para pharma/regulado, valídalo con tu abogado de IP.

## Consecuencias

- Un único punto de acoplamiento (`promcp/transport/fastmcp_adapter.py`).
- Los parches de seguridad llegan al regenerar el lockfile de forma deliberada.
- Migrar de transporte o pasar a modo vendor-auditado = tocar un archivo.
