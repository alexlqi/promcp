"""
proMCP — Proactive MCP Convention
===================================
Decorators, response contracts, registry, and linter for proMCP-compliant
MCP server tool design.

Spec    : https://github.com/alexlqi/promcp
Author  : @alexlqi (https://github.com/alexlqi)
Org     : EnthalpyDW / GoMethos
License : Apache 2.0

Quick start
-----------
    from promcp import read_tool, do_tool, can_do_tool
    from promcp.registry import default_registry
    from promcp.adapters.raw import to_dict

    @read_tool(description="Current stock level.", unit="units")
    def read_stock(sku: str, warehouse: str) -> dict:
        return {"value": db.get(sku, warehouse)}

    @do_tool(
        description="Transfer stock between warehouses.",
        compensable=True,
        side_effects=["stock_change_source", "stock_change_dest"],
        compensation_hint_template=(
            "do_transfer_stock sku={sku} quantity={quantity} "
            "source_warehouse={destination_warehouse} "
            "destination_warehouse={source_warehouse}"
        ),
    )
    def do_transfer_stock(
        sku: str, quantity: int,
        source_warehouse: str, destination_warehouse: str,
        idempotency_key: str,
    ) -> dict:
        prev = db.get(sku, source_warehouse)
        db.transfer(sku, quantity, source_warehouse, destination_warehouse)
        return {"applied_value": quantity, "previous_value": prev}

    @can_do_tool(description="Check feasibility. Call before any do_*.")
    def can_do(intent: dict, scope: list = None) -> dict:
        return {"candidates": matcher.match(intent), "blocked": []}

    # Export for any MCP framework
    tools = to_dict(default_registry)

    # Or lint the registry directly
    from promcp.linter import lint_registry
    results, server_findings = lint_registry(default_registry)
"""

from promcp.decorators import can_do_tool, do_tool, read_tool
from promcp.registry import Registry, default_registry

#: Package version. Until now it moved independently of SPEC.md, so nothing in a release
#: said which spec version it compiles against — while §14.1 obliges every extension to
#: declare exactly that. `__spec_version__` states it.
__version__      = "0.5.0"
__spec_version__ = "0.4.0"
__author__   = "@alexlqi"
__spec_url__ = "https://github.com/alexlqi/proMCP"

__all__ = [
    "read_tool",
    "do_tool",
    "can_do_tool",
    "Registry",
    "default_registry",
    "__version__",
    "__spec_version__",
]
