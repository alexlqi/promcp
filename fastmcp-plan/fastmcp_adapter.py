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

    Envuelve un `FastMCP` y expone la convención triádica. Registra las
    capacidades como tools MCP con prefijos canónicos `can_do__` / `read__` /
    `do__`, de modo que la semántica triádica sobreviva al cruce del transporte.
    """

    CAN_DO_PREFIX = "can_do__"
    READ_PREFIX = "read__"
    DO_PREFIX = "do__"

    def __init__(self, name: str, **fastmcp_kwargs: Any) -> None:
        # `_mcp` es el detalle de implementación; nadie fuera del adapter lo ve.
        self._mcp = _FastMCP(name, **fastmcp_kwargs)

    # -- Registro (composición, no herencia) ---------------------------------
    def register_can_do(self, capability: str) -> Callable[[Callable], Callable]:
        return self._mcp.tool(name=f"{self.CAN_DO_PREFIX}{capability}")

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
