"""
TMCP Decorators
---------------
@read_tool   — declares a side-effect-free observation tool
@do_tool     — declares a mutation tool with idempotency and compensation
@can_do_tool — declares the precondition/feasibility tool (singleton)

Each decorator:
  1. Validates naming and parameter contracts at decoration time (fail-fast)
  2. Wraps the function to enforce response contracts at call time
  3. Registers the tool in a Registry for adapter export and linting

Author : @alexlqi (https://github.com/alexlqi)
Org    : EnthalpyDW / GoMethos
Spec   : https://github.com/alexlqi/tmcp
"""

from __future__ import annotations

import functools
import inspect
import time
from typing import Any, Callable, Optional

from promcp.contracts import (
    CanDoResponseBuilder,
    DoResponseBuilder,
    ReadResponseBuilder,
)
from promcp.exceptions import DecoratorMisuseError
from promcp.registry import Registry, ToolEntry, default_registry


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _infer_input_schema(fn: Callable) -> dict:
    """
    Build a basic JSON Schema inputSchema from Python type annotations.
    Supports str, int, float, bool, list, dict, Optional[X].
    Falls back to {} for unannotated or complex types.
    """
    PY_TO_JSON = {
        str:   "string",
        int:   "integer",
        float: "number",
        bool:  "boolean",
        list:  "array",
        dict:  "object",
    }

    sig        = inspect.signature(fn)
    properties = {}
    required   = []

    for name, param in sig.parameters.items():
        if name == "self":
            continue

        ann = param.annotation
        if ann is inspect.Parameter.empty:
            properties[name] = {}
            if param.default is inspect.Parameter.empty:
                required.append(name)
            continue

        # Unwrap Optional[X] → X
        origin = getattr(ann, "__origin__", None)
        args   = getattr(ann, "__args__", ())
        is_optional = (
            origin is type(None)
            or (origin is not None and type(None) in args)
        )

        inner = ann
        if is_optional and args:
            inner = next((a for a in args if a is not type(None)), ann)

        json_type = PY_TO_JSON.get(inner)

        if json_type:
            prop: dict = {"type": json_type}
            if is_optional:
                prop = {"type": [json_type, "null"]}
            properties[name] = prop
        else:
            properties[name] = {}

        if param.default is inspect.Parameter.empty and not is_optional:
            required.append(name)

    schema: dict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _validate_prefix(name: str, expected_prefix: str, decorator: str) -> None:
    if not name.startswith(expected_prefix):
        raise DecoratorMisuseError(
            name,
            f"@{decorator} requires name to start with '{expected_prefix}'. "
            f"Rename the function or use the 'name' parameter.",
        )
    if not name.replace("_", "").replace(expected_prefix.replace("_", ""), "").strip():
        raise DecoratorMisuseError(
            name,
            f"@{decorator} tool name must have a capability identifier "
            f"after the '{expected_prefix}' prefix.",
        )


def _validate_snake_case(name: str) -> None:
    import re
    if not re.match(r'^[a-z][a-z0-9_]*$', name):
        raise DecoratorMisuseError(
            name,
            "Tool name must be lowercase_snake_case.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# @read_tool
# ─────────────────────────────────────────────────────────────────────────────

def read_tool(
    description: str,
    *,
    unit:     Optional[str] = None,
    name:     Optional[str] = None,
    registry: Registry      = default_registry,
):
    """
    Declare a TMCP read_* tool.

    The decorated function:
    - MUST be named read_<capability> (or provide name= override)
    - MUST have no side effects
    - MAY return a partial dict; missing fields are auto-completed:
        {"value": ...}
        → {"value": ..., "timestamp": <now>, "quality": "good", "unit": <unit>}
    - On unhandled exception: returns quality="error", value=null

    Parameters
    ----------
    description : str
        Human and LLM-readable description of what this tool observes.
        Include when NOT to use it.
    unit : str, optional
        Unit of measurement for the returned value (e.g. "celsius", "units").
    name : str, optional
        Override the tool name. Defaults to the function name.
    registry : Registry, optional
        Target registry. Defaults to the module-level default_registry.

    Example
    -------
    @read_tool(description="Current stock level for a SKU in a warehouse.", unit="units")
    def read_stock_warehouse(sku: str, warehouse: str) -> dict:
        return {"value": db.get_stock(sku, warehouse)}
    """
    def decorator(fn: Callable) -> Callable:
        tool_name = name or fn.__name__

        # Fail-fast validations at decoration time
        _validate_snake_case(tool_name)
        _validate_prefix(tool_name, "read_", "read_tool")

        builder      = ReadResponseBuilder(tool_name=tool_name, unit=unit)
        input_schema = _infer_input_schema(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            from promcp.exceptions import TMCPError
            try:
                raw = fn(*args, **kwargs)
                if not isinstance(raw, dict):
                    raw = {"value": raw}
                return builder.build(raw)
            except TMCPError:
                raise  # contract violations bubble up
            except Exception as exc:
                return builder.build({}, exc=exc)

        # Attach TMCP metadata to the wrapper for introspection
        wrapper.__tmcp_name__     = tool_name
        wrapper.__tmcp_category__ = "read"

        registry.register(ToolEntry(
            name=tool_name,
            category="read",
            fn=wrapper,
            description=description,
            unit=unit,
            input_schema=input_schema,
        ))

        return wrapper

    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# @do_tool
# ─────────────────────────────────────────────────────────────────────────────

def do_tool(
    description: str,
    *,
    compensable:  bool,
    side_effects: list[str]     = (),
    compensation_hint_template: Optional[str] = None,
    name:         Optional[str] = None,
    registry:     Registry      = default_registry,
):
    """
    Declare a TMCP do_* tool.

    The decorated function:
    - MUST be named do_<capability> (or provide name= override)
    - MUST declare idempotency_key as a parameter
    - MUST return a dict; missing required fields are auto-completed
    - On unhandled exception: returns status="failed", no side effects committed

    Parameters
    ----------
    description : str
        Human and LLM-readable description. Include when NOT to use it.
    compensable : bool
        Whether the mutation can be reversed. REQUIRED — no default.
        When True, provide compensation_hint_template or return
        compensation_hint in the function's dict.
    side_effects : list[str], optional
        Declared observable external changes produced by this mutation.
        E.g. ["stock_level_change", "audit_log_entry"].
    compensation_hint_template : str, optional
        Template string for the compensation call. Rendered with the
        call's kwargs at runtime.
        E.g. "do_transfer_stock sku={sku} quantity={quantity} source_warehouse={destination_warehouse} destination_warehouse={source_warehouse}"
    name : str, optional
        Override the tool name. Defaults to the function name.
    registry : Registry, optional
        Target registry. Defaults to the module-level default_registry.

    Example
    -------
    @do_tool(
        description="Transfer stock between warehouses.",
        compensable=True,
        side_effects=["stock_level_change_source", "stock_level_change_destination"],
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
        prev = db.get_stock(sku, source_warehouse)
        db.transfer(sku, quantity, source_warehouse, destination_warehouse)
        return {"applied_value": quantity, "previous_value": prev}
    """
    def decorator(fn: Callable) -> Callable:
        tool_name = name or fn.__name__

        # Fail-fast validations at decoration time
        _validate_snake_case(tool_name)
        _validate_prefix(tool_name, "do_", "do_tool")

        # Verify idempotency_key is a declared parameter
        sig    = inspect.signature(fn)
        params = list(sig.parameters.keys())
        if "idempotency_key" not in params:
            raise DecoratorMisuseError(
                tool_name,
                "Function must declare 'idempotency_key: str' as a parameter. "
                "TMCP requires every do_* to be idempotent by key.",
            )

        builder = DoResponseBuilder(
            tool_name=tool_name,
            compensable=compensable,
            side_effects=list(side_effects),
            compensation_hint_template=compensation_hint_template,
        )
        input_schema = _infer_input_schema(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # Bind args to get kwargs for compensation_hint template rendering
            try:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                call_kwargs = dict(bound.arguments)
            except TypeError:
                call_kwargs = kwargs

            idempotency_key = call_kwargs.get("idempotency_key", "")

            from promcp.exceptions import TMCPError
            try:
                raw = fn(*args, **kwargs)
                if not isinstance(raw, dict):
                    raw = {}
                return builder.build(raw, idempotency_key, call_kwargs)
            except TMCPError:
                raise
            except Exception as exc:
                return builder.build({}, idempotency_key, call_kwargs, exc=exc)

        wrapper.__tmcp_name__     = tool_name
        wrapper.__tmcp_category__ = "do"

        registry.register(ToolEntry(
            name=tool_name,
            category="do",
            fn=wrapper,
            description=description,
            compensable=compensable,
            side_effects=list(side_effects),
            compensation_hint_template=compensation_hint_template,
            input_schema=input_schema,
        ))

        return wrapper

    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# @can_do_tool
# ─────────────────────────────────────────────────────────────────────────────

def can_do_tool(
    description: str,
    *,
    registry: Registry = default_registry,
):
    """
    Declare the TMCP can_do tool (singleton per registry).

    The decorated function:
    - MUST be named exactly 'can_do'
    - MUST accept 'intent: dict' as a parameter
    - MAY return a partial dict; missing fields are auto-completed:
        {"candidates": [...], "blocked": [...]}
        → full CapabilityReport with query_id, feasible, context, metadata
    - feasible is AUTO-CALCULATED — never declare it manually
    - query_id is AUTO-GENERATED if absent
    - On unhandled exception: returns feasible=False with error in blocked[]

    Parameters
    ----------
    description : str
        Human and LLM-readable description. Include "Call before any do_*
        when permission or state is uncertain."
    registry : Registry, optional
        Target registry. Defaults to the module-level default_registry.

    Example
    -------
    @can_do_tool(
        description=(
            "Check feasibility of an intended action. "
            "Returns candidates with permission status and valid_until. "
            "Call before any do_* when permission or state is uncertain."
        )
    )
    def can_do(intent: dict, scope: list = None) -> dict:
        candidates = my_matcher.match(intent["semantic_tags"])
        blocked    = my_matcher.blocked(intent["semantic_tags"])
        return {"candidates": candidates, "blocked": blocked}
    """
    def decorator(fn: Callable) -> Callable:
        tool_name = fn.__name__

        # Singleton — must be named exactly "can_do"
        if tool_name != "can_do":
            raise DecoratorMisuseError(
                tool_name,
                "The @can_do_tool decorated function must be named exactly 'can_do'. "
                "There is exactly one can_do tool per TMCP server.",
            )

        # Verify intent parameter exists
        sig    = inspect.signature(fn)
        params = list(sig.parameters.keys())
        if "intent" not in params:
            raise DecoratorMisuseError(
                tool_name,
                "Function must declare 'intent: dict' as a parameter.",
            )

        builder      = CanDoResponseBuilder(tool_name=tool_name)
        input_schema = _infer_input_schema(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.monotonic()
            from promcp.exceptions import TMCPError
            try:
                raw = fn(*args, **kwargs)
                if not isinstance(raw, dict):
                    raw = {}
                latency_ms = int((time.monotonic() - t0) * 1000)
                return builder.build(raw, latency_ms=latency_ms)
            except TMCPError:
                raise
            except Exception as exc:
                latency_ms = int((time.monotonic() - t0) * 1000)
                return builder.build({}, latency_ms=latency_ms, exc=exc)

        wrapper.__tmcp_name__     = "can_do"
        wrapper.__tmcp_category__ = "can_do"

        registry.register(ToolEntry(
            name="can_do",
            category="can_do",
            fn=wrapper,
            description=description,
            input_schema=input_schema,
        ))

        return wrapper

    return decorator
