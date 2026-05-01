"""
TMCP Raw Adapter
----------------
Exports a Registry as a list of raw tool definition dicts.
Compatible with any MCP framework that accepts tool definitions as dicts,
and with tmcp-lint for static validation.

Author : @alexlqi (https://github.com/alexlqi)
Org    : EnthalpyDW / GoMethos
"""

from __future__ import annotations

from promcp.registry import Registry


def to_dict(registry: Registry) -> list[dict]:
    """
    Export all tools in the registry as raw tool definition dicts.

    The output is a list compatible with:
    - tmcp-lint (pass directly as the tools list)
    - Any MCP framework that accepts dict-based tool definitions
    - JSON serialization for API exposure

    Example
    -------
    from promcp.adapters.raw import to_dict
    from promcp.registry import default_registry

    tools = to_dict(default_registry)
    # → [{"name": "read_stock", "description": "...", "inputSchema": {...}, "responseSchema": {...}}, ...]
    """
    return registry.to_list()


def to_callable_map(registry: Registry) -> dict[str, callable]:
    """
    Export all tools as a name → callable mapping.
    Useful for dispatch in custom MCP server implementations.

    Example
    -------
    handlers = to_callable_map(default_registry)
    result   = handlers["read_stock_warehouse"](sku="SKU-001", warehouse="A")
    """
    return {entry.name: entry.fn for entry in registry.all()}
