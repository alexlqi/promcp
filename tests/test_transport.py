"""
Tests for the FastMCP transport boundary (`promcp.transport`).

Hermetic: FastMCP is never actually driven. `_FastMCP` is replaced by a stub
that records the `name=` passed to `.tool(...)`, so these tests validate the
naming convention emitted by `register_*` and the ImportError contract without
requiring `fastmcp` at runtime.

Author : @alexlqi (https://github.com/alexlqi)
"""

import importlib
import sys

import pytest

from promcp.linter.checker import Severity, check_naming

MODULE = "promcp.transport.fastmcp_adapter"


class _FakeFastMCP:
    """Stub de FastMCP: registra los nombres pasados a `.tool(name=...)`."""

    def __init__(self, name: str, **kwargs) -> None:
        self.name = name
        self.registered: list[str] = []

    def tool(self, name: str):
        self.registered.append(name)

        def _decorator(fn):
            return fn

        return _decorator


@pytest.fixture()
def server(monkeypatch):
    """ProMCPServer respaldado por el stub, sin tocar el FastMCP real."""
    import types

    fake_fastmcp = types.ModuleType("fastmcp")
    fake_fastmcp.FastMCP = _FakeFastMCP
    monkeypatch.setitem(sys.modules, "fastmcp", fake_fastmcp)

    mod = importlib.reload(importlib.import_module(MODULE))
    return mod.ProMCPServer("test-server")


# ── naming convention ────────────────────────────────────────────────────────

def test_register_emits_promcp_names(server):
    @server.register_can_do()
    def can_do(intent: dict) -> dict:
        return {"candidates": [], "blocked": []}

    @server.register_read("stock")
    def read_stock(sku: str) -> dict:
        return {"value": 1}

    @server.register_do("transfer")
    def do_transfer(sku: str, idempotency_key: str) -> dict:
        return {"applied_value": 1}

    # exactly `can_do` (singleton), single-underscore read_/do_ prefixes
    assert server.raw.registered == ["can_do", "read_stock", "do_transfer"]


def test_emitted_names_pass_the_promcp_linter(server):
    @server.register_can_do()
    def can_do(intent: dict) -> dict:
        return {}

    @server.register_read("stock_level")
    def read_stock_level(sku: str) -> dict:
        return {}

    @server.register_do("transfer_stock")
    def do_transfer_stock(sku: str, idempotency_key: str) -> dict:
        return {}

    for name in server.raw.registered:
        errors = [f for f in check_naming({"name": name})
                  if f.severity is Severity.ERROR]
        assert errors == [], f"{name!r} failed check_naming: {errors}"


def test_can_do_is_a_singleton_not_per_capability(server):
    # register_can_do takes no capability argument
    with pytest.raises(TypeError):
        server.register_can_do("transfer")  # type: ignore[call-arg]


# ── ImportError contract ─────────────────────────────────────────────────────

def test_missing_fastmcp_raises_actionable_importerror(monkeypatch):
    # Force `import fastmcp` to fail, then reload the adapter module.
    monkeypatch.setitem(sys.modules, "fastmcp", None)
    try:
        with pytest.raises(ImportError) as excinfo:
            importlib.reload(importlib.import_module(MODULE))
        assert "promcp[transport]" in str(excinfo.value)
    finally:
        # Restore a clean, importable module for the rest of the suite.
        import types

        fake_fastmcp = types.ModuleType("fastmcp")
        fake_fastmcp.FastMCP = _FakeFastMCP
        monkeypatch.setitem(sys.modules, "fastmcp", fake_fastmcp)
        importlib.reload(importlib.import_module(MODULE))
