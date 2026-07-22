"""
promcp.transport — frontera de transporte de ProMCP.

Este paquete es la ÚNICA superficie por la que ProMCP habla con un transporte
MCP concreto. El resto del codebase importa desde aquí (`promcp.transport`),
nunca `fastmcp` directamente. Cambiar de transporte, pinnear otra versión o
vendorizar para air-gap = tocar `fastmcp_adapter.py` y nada más.

Ver ADR-001 (fastmcp-plan/), ../../NOTICE y
../../THIRD_PARTY_LICENSES/fastmcp.txt.
"""
from __future__ import annotations

from promcp.transport.fastmcp_adapter import ProMCPServer, TriadicSurface

__all__ = ["ProMCPServer", "TriadicSurface"]
