"""
Tests for proMCP decorators.

Author : @alexlqi (https://github.com/alexlqi)
"""

from typing import Any, Dict, List, Optional

import pytest
from promcp import read_tool, do_tool, can_do_tool
from promcp.decorators import _infer_input_schema
from promcp.registry import Registry
from promcp.exceptions import (
    ContractViolation,
    DecoratorMisuseError,
    CanDoSingletonError,
    InvalidQualityError,
    InvalidStatusError,
)


# ─────────────────────────────────────────────────────────────────────────────
# @read_tool
# ─────────────────────────────────────────────────────────────────────────────

class TestReadTool:

    def test_basic_response_shape(self):
        reg = Registry("test_read_basic")

        @read_tool(description="Read stock.", unit="units", registry=reg)
        def read_stock(sku: str) -> dict:
            return {"value": 100}

        result = read_stock(sku="SKU-001")
        assert result["value"] == 100
        assert result["quality"] == "good"
        assert result["unit"] == "units"
        assert "timestamp" in result

    def test_non_dict_return_is_wrapped(self):
        reg = Registry("test_read_scalar")

        @read_tool(description="Read temp.", registry=reg)
        def read_temperature() -> dict:
            return 24.7  # non-dict scalar

        result = read_temperature()
        assert result["value"] == 24.7
        assert result["quality"] == "good"

    def test_exception_returns_error_quality(self):
        reg = Registry("test_read_exc")

        @read_tool(description="Failing read.", registry=reg)
        def read_broken() -> dict:
            raise ConnectionError("sensor offline")

        result = read_broken()
        assert result["quality"] == "error"
        assert result["value"] is None

    def test_custom_quality_passthrough(self):
        reg = Registry("test_read_quality")

        @read_tool(description="Stale read.", registry=reg)
        def read_stale_data() -> dict:
            return {"value": 99, "quality": "stale"}

        result = read_stale_data()
        assert result["quality"] == "stale"

    def test_invalid_quality_raises(self):
        reg = Registry("test_read_invalid_q")

        @read_tool(description="Bad quality.", registry=reg)
        def read_bad_quality() -> dict:
            return {"value": 1, "quality": "unknown_value"}

        with pytest.raises(InvalidQualityError):
            read_bad_quality()

    def test_wrong_prefix_raises(self):
        reg = Registry("test_read_prefix")
        with pytest.raises(DecoratorMisuseError, match="read_"):
            @read_tool(description="Bad name.", registry=reg)
            def get_temperature() -> dict:
                return {"value": 1}

    def test_uppercase_name_raises(self):
        reg = Registry("test_read_case")
        with pytest.raises(DecoratorMisuseError, match="lowercase_snake_case"):
            @read_tool(description="Bad case.", registry=reg)
            def Read_Stock() -> dict:
                return {"value": 1}

    def test_unit_from_decorator_not_overridden_by_return(self):
        reg = Registry("test_read_unit")

        @read_tool(description="Read pressure.", unit="pascal", registry=reg)
        def read_pressure() -> dict:
            return {"value": 101325}

        result = read_pressure()
        assert result["unit"] == "pascal"

    def test_unit_in_return_overrides_decorator(self):
        reg = Registry("test_read_unit_override")

        @read_tool(description="Read temp.", unit="celsius", registry=reg)
        def read_temp_override() -> dict:
            return {"value": 24.7, "unit": "fahrenheit"}

        result = read_temp_override()
        assert result["unit"] == "fahrenheit"

    def test_registered_in_registry(self):
        reg = Registry("test_read_reg")

        @read_tool(description="Registered read.", registry=reg)
        def read_registered_thing() -> dict:
            return {"value": 1}

        entry = reg.get("read_registered_thing")
        assert entry is not None
        assert entry.category == "read"

    def test_extension_fields_passthrough(self):
        reg = Registry("test_read_ext")

        @read_tool(description="Physical sensor.", registry=reg)
        def read_sensor_physical() -> dict:
            return {"value": 25.0, "node_id": "node_007"}

        result = read_sensor_physical()
        assert result["node_id"] == "node_007"


# ─────────────────────────────────────────────────────────────────────────────
# @do_tool
# ─────────────────────────────────────────────────────────────────────────────

class TestDoTool:

    def test_basic_response_shape(self):
        reg = Registry("test_do_basic")

        @do_tool(
            description="Transfer stock.",
            compensable=True,
            side_effects=["stock_change"],
            compensation_hint_template="do_transfer_stock sku={sku} quantity={quantity} source_warehouse={destination_warehouse} destination_warehouse={source_warehouse}",
            registry=reg,
        )
        def do_transfer_stock(
            sku: str, quantity: int,
            source_warehouse: str, destination_warehouse: str,
            idempotency_key: str,
        ) -> dict:
            return {"applied_value": quantity, "previous_value": 0}

        result = do_transfer_stock(
            sku="SKU-001", quantity=50,
            source_warehouse="A", destination_warehouse="B",
            idempotency_key="test-key-001",
        )

        assert result["status"] == "success"
        assert result["idempotency_key"] == "test-key-001"
        assert result["compensable"] is True
        assert result["applied_value"] == 50
        assert result["previous_value"] == 0
        assert "stock_change" in result["side_effects"]
        assert "timestamp" in result
        assert "do_transfer_stock" in result["compensation_hint"]

    def test_exception_returns_failed_status(self):
        reg = Registry("test_do_exc")

        @do_tool(description="Failing do.", compensable=False, registry=reg)
        def do_failing_op(idempotency_key: str) -> dict:
            raise RuntimeError("db error")

        result = do_failing_op(idempotency_key="key-002")
        assert result["status"] == "failed"
        assert result["idempotency_key"] == "key-002"
        assert result["side_effects"] == []

    def test_missing_idempotency_key_param_raises(self):
        reg = Registry("test_do_no_key")
        with pytest.raises(DecoratorMisuseError, match="idempotency_key"):
            @do_tool(description="No key.", compensable=False, registry=reg)
            def do_no_idempotency(value: str) -> dict:
                return {}

    def test_wrong_prefix_raises(self):
        reg = Registry("test_do_prefix")
        with pytest.raises(DecoratorMisuseError, match="do_"):
            @do_tool(description="Bad name.", compensable=False, registry=reg)
            def update_stock(idempotency_key: str) -> dict:
                return {}

    def test_compensable_false_no_hint_required(self):
        reg = Registry("test_do_no_hint")

        @do_tool(description="Irreversible.", compensable=False, registry=reg)
        def do_delete_record(record_id: str, idempotency_key: str) -> dict:
            return {}

        result = do_delete_record(record_id="R1", idempotency_key="key-003")
        assert result["compensable"] is False
        assert result["compensation_hint"] is None

    def test_invalid_status_raises(self):
        reg = Registry("test_do_invalid_status")

        @do_tool(description="Bad status.", compensable=False, registry=reg)
        def do_bad_status(idempotency_key: str) -> dict:
            return {"status": "unknown_status"}

        with pytest.raises(InvalidStatusError):
            do_bad_status(idempotency_key="key-004")

    def test_side_effects_from_decorator_used_when_not_in_return(self):
        reg = Registry("test_do_se_decorator")

        @do_tool(
            description="Side effects from decorator.",
            compensable=False,
            side_effects=["audit_log", "notification_sent"],
            registry=reg,
        )
        def do_notify(user_id: str, idempotency_key: str) -> dict:
            return {}  # no side_effects in return

        result = do_notify(user_id="U1", idempotency_key="key-005")
        assert "audit_log" in result["side_effects"]
        assert "notification_sent" in result["side_effects"]

    def test_registered_in_registry(self):
        reg = Registry("test_do_reg")

        @do_tool(description="Registered do.", compensable=False, registry=reg)
        def do_registered_action(idempotency_key: str) -> dict:
            return {}

        entry = reg.get("do_registered_action")
        assert entry is not None
        assert entry.category == "do"
        assert entry.compensable is False


# ─────────────────────────────────────────────────────────────────────────────
# @can_do_tool
# ─────────────────────────────────────────────────────────────────────────────

class TestCanDoTool:

    def test_basic_response_shape(self):
        reg = Registry("test_can_do_basic")

        @can_do_tool(description="Check feasibility.", registry=reg)
        def can_do(intent: dict, scope: list = None) -> dict:
            return {
                "candidates": [{
                    "capability":  "do_transfer_stock",
                    "source":      "inventory-server",
                    "confidence":  0.95,
                    "permission":  "allowed",
                    "valid_until": "2099-01-01T00:00:00Z",
                }],
                "blocked": [],
            }

        result = can_do(intent={"semantic_tags": ["inventory"]})
        assert result["feasible"] is True
        assert len(result["candidates"]) == 1
        assert "query_id" in result
        assert "metadata" in result
        assert result["metadata"]["total_latency_ms"] >= 0

    def test_feasible_auto_calculated_true(self):
        reg = Registry("test_can_do_feasible_true")

        @can_do_tool(description="Auto feasible true.", registry=reg)
        def can_do(intent: dict) -> dict:
            return {
                "candidates": [{"capability": "do_x", "source": "s",
                                 "confidence": 1.0, "permission": "allowed",
                                 "valid_until": "2099-01-01T00:00:00Z"}],
                "blocked": [],
            }

        result = can_do(intent={"semantic_tags": ["x"]})
        assert result["feasible"] is True

    def test_feasible_auto_calculated_false_when_no_allowed(self):
        reg = Registry("test_can_do_feasible_false")

        @can_do_tool(description="Auto feasible false.", registry=reg)
        def can_do(intent: dict) -> dict:
            return {
                "candidates": [],
                "blocked": [{"capability": "do_x", "source": "s",
                              "permission": "rate_limited", "reason": "limit hit"}],
            }

        result = can_do(intent={"semantic_tags": ["x"]})
        assert result["feasible"] is False

    def test_query_id_auto_generated(self):
        reg = Registry("test_can_do_qid")

        @can_do_tool(description="Auto query_id.", registry=reg)
        def can_do(intent: dict) -> dict:
            return {"candidates": [], "blocked": []}

        r1 = can_do(intent={"semantic_tags": ["x"]})
        r2 = can_do(intent={"semantic_tags": ["x"]})
        assert "query_id" in r1
        assert r1["query_id"] != r2["query_id"]  # unique per call

    def test_exception_returns_feasible_false(self):
        """An unreachable source is unroutable, not blocked (spec §6.3).

        This test previously asserted a blocked[] entry with `capability: "unknown"`.
        That was the workaround for a gap in the spec, and asserting it pinned the gap
        in place: `blocked[]` types its first field as a capability, and "unknown" is
        not one. Nothing could be evaluated, so there is no capability to name.
        """
        reg = Registry("test_can_do_exc")

        @can_do_tool(description="Failing can_do.", registry=reg)
        def can_do(intent: dict) -> dict:
            raise ConnectionError("mesh unreachable")

        result = can_do(intent={"semantic_tags": ["x"]})
        assert result["feasible"] is False
        assert result["blocked"] == []
        assert len(result["unroutable"]) == 1
        assert result["unroutable"][0]["reason"] == "requirements_unmet"
        assert "mesh unreachable" in result["unroutable"][0]["detail"]

    def test_unroutable_explains_an_infeasible_report(self):
        """§12.2 demands `feasible: false` be explained; §6.3 gives it the vocabulary."""
        reg = Registry("test_can_do_unroutable")

        @can_do_tool(description="Nothing produces this.", registry=reg)
        def can_do(intent: dict) -> dict:
            return {
                "candidates": [],
                "blocked": [],
                "unroutable": [{
                    "outcome": "stock_level",
                    "reason": "no_producer",
                    "detail": "no declared capability produces stock_level",
                }],
            }

        result = can_do(intent={"semantic_tags": ["stock"]})
        assert result["feasible"] is False
        assert result["unroutable"][0]["reason"] == "no_producer"

    def test_unroutable_rejects_unknown_reason(self):
        reg = Registry("test_can_do_unroutable_bad")

        @can_do_tool(description="Bad reason.", registry=reg)
        def can_do(intent: dict) -> dict:
            return {"unroutable": [{"outcome": "x", "reason": "made_up", "detail": "d"}]}

        with pytest.raises(ContractViolation, match="made_up"):
            can_do(intent={"semantic_tags": ["x"]})

    def test_feasible_and_unroutable_are_mutually_exclusive(self):
        """A report cannot claim a route and record that the outcome is unreachable."""
        reg = Registry("test_can_do_contradiction")

        @can_do_tool(description="Contradictory.", registry=reg)
        def can_do(intent: dict) -> dict:
            return {
                "candidates": [{
                    "capability": "read_stock", "source": "wms", "confidence": 0.9,
                    "permission": "allowed", "valid_until": "2026-01-01T00:00:00Z",
                }],
                "unroutable": [{"outcome": "x", "reason": "no_producer", "detail": "d"}],
            }

        with pytest.raises(ContractViolation, match="unroutable"):
            can_do(intent={"semantic_tags": ["x"]})

    def test_wrong_name_raises(self):
        reg = Registry("test_can_do_name")
        with pytest.raises(DecoratorMisuseError, match="can_do"):
            @can_do_tool(description="Wrong name.", registry=reg)
            def check_feasibility(intent: dict) -> dict:
                return {}

    def test_missing_intent_param_raises(self):
        reg = Registry("test_can_do_intent")
        with pytest.raises(DecoratorMisuseError, match="intent"):
            @can_do_tool(description="No intent.", registry=reg)
            def can_do(query: dict) -> dict:
                return {}

    def test_singleton_enforced(self):
        reg = Registry("test_can_do_singleton")

        @can_do_tool(description="First.", registry=reg)
        def can_do(intent: dict) -> dict:
            return {"candidates": [], "blocked": []}

        with pytest.raises(CanDoSingletonError):
            @can_do_tool(description="Second — should fail.", registry=reg)
            def can_do(intent: dict) -> dict:  # noqa: F811
                return {"candidates": [], "blocked": []}


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistry:

    def test_to_list_includes_response_schema(self):
        reg = Registry("test_reg_schema")

        @read_tool(description="Read X.", registry=reg)
        def read_x() -> dict:
            return {"value": 1}

        dicts = reg.to_list()
        assert len(dicts) == 1
        assert "responseSchema" in dicts[0]
        props = dicts[0]["responseSchema"]["properties"]
        assert "quality" in props
        assert "value" in props

    def test_lint_registry_passes_for_compliant_server(self):
        from promcp.linter import lint_registry
        reg = Registry("test_lint_compliant")

        @read_tool(description="Read stock level for a SKU.", unit="units", registry=reg)
        def read_stock_level(sku: str) -> dict:
            return {"value": 100}

        @do_tool(
            description="Transfer stock between warehouses.",
            compensable=True,
            side_effects=["stock_change"],
            compensation_hint_template="do_transfer_stock sku={sku}",
            registry=reg,
        )
        def do_transfer_stock(sku: str, idempotency_key: str) -> dict:
            return {"applied_value": 10, "previous_value": 0}

        @can_do_tool(description="Check feasibility. Call before any do_*.", registry=reg)
        def can_do(intent: dict) -> dict:
            return {"candidates": [], "blocked": []}

        tool_results, server_findings = lint_registry(reg)
        errors = [f for f in server_findings if f.severity.value == "error"]
        for r in tool_results:
            errors += [f for f in r.findings if f.severity.value == "error"]

        assert errors == [], f"Expected no errors, got: {[e.message for e in errors]}"


# ─────────────────────────────────────────────────────────────────────────────
# inputSchema inference — regression suite for ADR-002
#
# Every case below produced an empty schema ({}) before 0.3.1. The empty schema
# was silent: no error, no warning — it surfaced later as a misleading linter
# diagnostic (I002 on can_do) pointing at a field the author never declared.
# ─────────────────────────────────────────────────────────────────────────────

class TestInputSchemaInference:

    @staticmethod
    def _schema(fn):
        return _infer_input_schema(fn)["properties"]

    # -- The five failure classes ---------------------------------------------

    def test_pep563_deferred_annotations(self):
        """`from __future__ import annotations` turns every annotation into a
        string. Before the fix this emptied EVERY parameter of the module."""
        src = (
            "from __future__ import annotations\n"
            "from typing import Optional\n"
            "def f(intent: dict, name: str, n: int, flag: bool,\n"
            "      scope: Optional[list[str]] = None) -> dict: ...\n"
        )
        ns = {}
        exec(compile(src, "<deferred>", "exec"), ns)

        props = self._schema(ns["f"])
        assert props["intent"] == {"type": "object"}
        assert props["name"] == {"type": "string"}
        assert props["n"] == {"type": "integer"}
        assert props["flag"] == {"type": "boolean"}
        assert props["scope"]["type"] == ["array", "null"]
        assert not any(p == {} for p in props.values())

    def test_pep585_builtin_generics(self):
        def f(tags: list[str], meta: dict[str, Any]) -> dict: ...

        props = self._schema(f)
        assert props["tags"] == {"type": "array", "items": {"type": "string"}}
        assert props["meta"] == {"type": "object"}

    def test_typing_generics(self):
        def f(tags: List[str], meta: Dict[str, Any]) -> dict: ...

        props = self._schema(f)
        assert props["tags"] == {"type": "array", "items": {"type": "string"}}
        assert props["meta"] == {"type": "object"}

    def test_pep604_unions(self):
        """`str | None` is types.UnionType and has no __origin__ attribute the
        old code could match on."""
        src = "def f(name: str | None = None) -> dict: ...\n"
        ns = {}
        exec(compile(src, "<union>", "exec"), ns)

        assert self._schema(ns["f"])["name"] == {"type": ["string", "null"]}

    def test_optional_generic_composition(self):
        def f(tags: Optional[list[str]] = None) -> dict: ...

        assert self._schema(f)["tags"] == {
            "type": ["array", "null"],
            "items": {"type": "string"},
        }

    # -- Behaviour preserved ---------------------------------------------------

    def test_bare_builtin_types_still_work(self):
        def f(a: str, b: int, c: float, d: bool, e: list, g: dict) -> dict: ...

        props = self._schema(f)
        assert [props[k]["type"] for k in "abcdeg"] == [
            "string", "integer", "number", "boolean", "array", "object",
        ]

    def test_unannotated_parameter_stays_empty(self):
        def f(a, b: str = "x") -> dict: ...

        assert self._schema(f)["a"] == {}

    def test_unresolvable_annotation_degrades_without_raising(self):
        """A type that cannot be resolved must yield {} — never an exception at
        decoration time. Worst case, the patch ties with the old behaviour."""
        src = (
            "from __future__ import annotations\n"
            "def f(x: SomeTypeThatDoesNotExist) -> dict: ...\n"
        )
        ns = {}
        exec(compile(src, "<unresolvable>", "exec"), ns)

        assert self._schema(ns["f"])["x"] == {}

    def test_untyped_generic_item_omits_items_key(self):
        def f(rows: list) -> dict: ...

        assert self._schema(f)["rows"] == {"type": "array"}

    # -- required ---------------------------------------------------------------

    def test_optional_without_default_is_required(self):
        """Nullability and presence are different things: Optional[str] with no
        default is a mandatory argument that accepts None. Declaring it optional
        made models omit it and the call fail with TypeError."""
        def f(a: Optional[str], b: str = "x") -> dict: ...

        assert _infer_input_schema(f)["required"] == ["a"]

    def test_defaults_are_never_required(self):
        def f(a: str = "x", b: Optional[int] = None) -> dict: ...

        assert "required" not in _infer_input_schema(f)

    # -- Varargs -----------------------------------------------------------------

    def test_varargs_and_kwargs_are_skipped(self):
        """*args/**kwargs cannot be expressed in JSON Schema properties."""
        def f(a: str, *args, **kwargs) -> dict: ...

        assert set(self._schema(f)) == {"a"}

    # -- End-to-end through the decorators ---------------------------------------

    def test_can_do_under_pep563_registers_a_typed_intent(self):
        """The bug that surfaced this ADR: a correct can_do declared in a module
        with PEP 563 failed the linter with I002 about 'semantic_tags'."""
        src = (
            "from __future__ import annotations\n"
            "from typing import Optional\n"
            "def can_do(intent: dict, scope: Optional[list[str]] = None) -> dict:\n"
            "    return {'candidates': [], 'blocked': []}\n"
        )
        ns = {}
        exec(compile(src, "<candomod>", "exec"), ns)

        reg = Registry("test_can_do_pep563")
        can_do_tool(description="Check feasibility.", registry=reg)(ns["can_do"])

        intent = reg.get("can_do").input_schema["properties"]["intent"]
        assert intent == {"type": "object"}

    def test_do_tool_under_pep563_types_idempotency_key(self):
        src = (
            "from __future__ import annotations\n"
            "from typing import Optional\n"
            "def do_thing(idempotency_key: str, tags: Optional[list[str]] = None) -> dict:\n"
            "    return {}\n"
        )
        ns = {}
        exec(compile(src, "<domod>", "exec"), ns)

        reg = Registry("test_do_pep563")
        do_tool(description="Do a thing.", compensable=False, registry=reg)(ns["do_thing"])

        props = reg.get("do_thing").input_schema["properties"]
        assert props["idempotency_key"] == {"type": "string"}
        assert props["tags"]["type"] == ["array", "null"]
