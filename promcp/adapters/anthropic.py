"""
proMCP → Anthropic MCP SDK Adapter
------------------------------------
Converts a proMCP Registry into an mcp.Server instance using the
official Anthropic MCP Python SDK.

Install the SDK: pip install mcp

Author : @alexlqi (https://github.com/alexlqi)
Org    : EnthalpyDW / GoMethos
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from promcp.registry import Registry

if TYPE_CHECKING:
    pass


def to_mcp_server(registry: Registry, server_name: str = "promcp-server"):
    """
    Convert a proMCP Registry to an mcp.Server instance.

    Requires: pip install mcp

    Parameters
    ----------
    registry    : Registry
        The proMCP registry containing decorated tools.
    server_name : str
        Name for the MCP server instance.

    Returns
    -------
    mcp.Server
        Configured server with all registered tools.

    Example
    -------
    from promcp.adapters.anthropic import to_mcp_server
    from promcp.registry import default_registry

    server = to_mcp_server(default_registry, server_name="inventory-server")

    if __name__ == "__main__":
        import mcp
        mcp.run(server)
    """
    try:
        import mcp
        import mcp.server
        import mcp.types as types
    except ImportError as e:
        raise ImportError(
            "The Anthropic MCP SDK is required for this adapter. "
            "Install it with: pip install mcp"
        ) from e

    server = mcp.server.Server(server_name)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        tools = []
        for entry in registry.all():
            tools.append(types.Tool(
                name=entry.name,
                description=entry.description,
                inputSchema=entry.input_schema,
            ))
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        entry = registry.get(name)
        if entry is None:
            raise ValueError(f"Unknown tool: {name}")

        import inspect
        result = entry.fn(**arguments)
        if inspect.isawaitable(result):
            result = await result

        import json
        return [types.TextContent(type="text", text=json.dumps(result))]

    return server
