"""
ProMCP · Transport adapter over FastMCP.

Incorporación de FastMCP como *adapter de transporte* de ProMCP, siguiendo
arquitectura outside-in / contract-first:

    dominio (invariantes, casos de uso)
        └── superficie triádica ProMCP  (can_do / read_* / do_*)
                └── ESTE adapter        (traducción a transporte MCP)
                        └── FastMCP      (plomería MCP: framing, handlers, auth)

FastMCP queda detrás de esta frontera. El resto del codebase NO importa
`fastmcp` directamente: importa `promcp.transport`. Así, si algún día cambias
de transporte (o pinneas otra versión, o lo vendorizas para air-gap), tocas
un solo archivo y no 40.

Licencia de FastMCP: Apache-2.0 (Prefect Technologies / Jeremiah Lowin).
Ver ../../NOTICE y ../../THIRD_PARTY_LICENSES/fastmcp.txt.

Autor de este adapter: Alejandro Andrade — @alexlqi — https://github.com/alexlqi
"""
from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

# --- Única frontera de acoplamiento con FastMCP -----------------------------
# Se importa aquí y SOLO aquí. Cualquier símbolo de FastMCP que ProMCP use
# debe re-exportarse desde este módulo, nunca importarse suelto en el codebase.
try:
    from fastmcp import FastMCP as _FastMCP
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "ProMCP requiere FastMCP como dependencia de transporte. "
        "Instala el extra: `pip install 'promcp[transport]'` "
        "o directamente `pip install 'fastmcp>=3.4,<4'`."
    ) from exc


@runtime_checkable
class TriadicSurface(Protocol):
    """Contrato mínimo que ProMCP espera de cualquier transporte.

    Mantener esto como Protocol (no como clase base) es deliberado: el día que
    quieras un transporte alterno (stdio propio, gRPC, un mock para tests),
    solo tiene que *cumplir* esta forma, no heredar de FastMCP.
    """

    def can_do(self, capability: str, /, **ctx: Any) -> bool: ...
    def read(self, resource: str, /, **params: Any) -> Any: ...
    def do(self, action: str, /, **payload: Any) -> Any: ...


class ProMCPServer:
    """Servidor ProMCP.

    Envuelve un `FastMCP` y expone la convención triádica usando los MISMOS
    nombres que exigen `promcp.decorators` y `promcp.linter.checker`: tools
    `read_<capacidad>` / `do_<capacidad>` (un solo guion bajo) y un único tool
    de feasibility llamado exactamente `can_do` (singleton). Así, un servidor
    exportado por este adapter pasa el propio linter de ProMCP —la semántica
    triádica sobrevive el cruce del transporte y sigue siendo compliant.
    """

    # `can_do` es un singleton por servidor (no lleva sufijo de capacidad);
    # `read_`/`do_` son prefijos con un solo guion bajo. Ver checker.VALID_PREFIXES
    # y checker.EXACT_GENERIC.
    CAN_DO_NAME = "can_do"
    READ_PREFIX = "read_"
    DO_PREFIX = "do_"

    def __init__(self, name: str, **fastmcp_kwargs: Any) -> None:
        # `_mcp` es el detalle de implementación; nadie fuera del adapter lo ve.
        self._mcp = _FastMCP(name, **fastmcp_kwargs)

    # -- Registro (composición, no herencia) ---------------------------------
    def register_can_do(self) -> Callable[[Callable], Callable]:
        """Registra el tool de feasibility `can_do` (singleton, uno por servidor)."""
        return self._mcp.tool(name=self.CAN_DO_NAME)

    def register_read(self, resource: str) -> Callable[[Callable], Callable]:
        return self._mcp.tool(name=f"{self.READ_PREFIX}{resource}")

    def register_do(self, action: str) -> Callable[[Callable], Callable]:
        return self._mcp.tool(name=f"{self.DO_PREFIX}{action}")

    # -- Escotilla de escape controlada --------------------------------------
    @property
    def raw(self) -> _FastMCP:
        """Acceso explícito al FastMCP subyacente.

        Existe a propósito y es feo a propósito: si en el codebase ves `.raw`,
        sabes que ahí hay acoplamiento directo al transporte que algún día
        habrá que pagar. Es tu marcador de deuda técnica, auditable con grep.
        """
        return self._mcp

    def run(self, *args: Any, **kwargs: Any) -> None:
        self._mcp.run(*args, **kwargs)


__all__ = ["ProMCPServer", "TriadicSurface"]
