"""
Tests for TMCP decorators.

Author : @alexlqi (https://github.com/alexlqi)
"""

import pytest
from promcp import read_tool, do_tool, can_do_tool
from promcp.registry import Registry
from promcp.exceptions import (
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
        reg = Registry("test_can_do_exc")

        @can_do_tool(description="Failing can_do.", registry=reg)
        def can_do(intent: dict) -> dict:
            raise ConnectionError("mesh unreachable")

        result = can_do(intent={"semantic_tags": ["x"]})
        assert result["feasible"] is False
        assert len(result["blocked"]) == 1
        assert result["blocked"][0]["permission"] == "source_unreachable"

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
