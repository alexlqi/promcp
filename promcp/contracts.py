"""
TMCP Contracts
--------------
TypedDicts and dataclasses representing the canonical response shapes
defined in the TMCP v0.2.0 specification.

These are used both by the decorators (runtime enforcement) and by the
linter (static validation).

Author : @alexlqi (https://github.com/alexlqi)
Org    : EnthalpyDW / GoMethos
Spec   : https://github.com/alexlqi/tmcp
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from typing_extensions import TypedDict


# ─────────────────────────────────────────────────────────────────────────────
# Enums (as Literal types for TypedDict compatibility)
# ─────────────────────────────────────────────────────────────────────────────

Quality    = Literal["good", "stale", "degraded", "error"]
Status     = Literal["success", "partial", "failed"]
Permission = Literal[
    "allowed",
    "requires_human_approval",
    "policy_denied",
    "rate_limited",
    "cooldown_active",
    "out_of_range",
    "permission_insufficient",
    "source_unreachable",
    "partition_no_quorum",
]

QUALITY_VALUES: frozenset[str] = frozenset(
    {"good", "stale", "degraded", "error"}
)
STATUS_VALUES: frozenset[str] = frozenset(
    {"success", "partial", "failed"}
)
PERMISSION_VALUES: frozenset[str] = frozenset({
    "allowed", "requires_human_approval", "policy_denied",
    "rate_limited", "cooldown_active", "out_of_range",
    "permission_insufficient", "source_unreachable", "partition_no_quorum",
})


# ─────────────────────────────────────────────────────────────────────────────
# read_* response
# ─────────────────────────────────────────────────────────────────────────────

class ReadResponse(TypedDict, total=False):
    value:     Any           # required
    timestamp: str           # required — ISO 8601
    quality:   Quality       # required
    unit:      Optional[str] # optional


@dataclass
class ReadResponseBuilder:
    """
    Builds a compliant ReadResponse from a partial dict returned by
    a @read_tool implementation.

    The implementation only needs to return {"value": ...}.
    Everything else is injected automatically.
    """
    tool_name: str
    unit:      Optional[str] = None

    def build(self, raw: dict, exc: Optional[Exception] = None) -> ReadResponse:
        if exc is not None:
            return ReadResponse(
                value=None,
                timestamp=_now(),
                quality="error",
                unit=self.unit,
            )

        quality = raw.get("quality", "good")

        from promcp.exceptions import InvalidQualityError
        if quality not in QUALITY_VALUES:
            raise InvalidQualityError(self.tool_name, quality)

        result: ReadResponse = {
            "value":     raw.get("value"),
            "timestamp": raw.get("timestamp", _now()),
            "quality":   quality,
        }
        unit = raw.get("unit", self.unit)
        if unit is not None:
            result["unit"] = unit

        # Pass through any domain extension fields
        for k, v in raw.items():
            if k not in result:
                result[k] = v

        return result


# ─────────────────────────────────────────────────────────────────────────────
# do_* response
# ─────────────────────────────────────────────────────────────────────────────

class DoResponse(TypedDict, total=False):
    status:            Status        # required
    idempotency_key:   str           # required
    compensable:       bool          # required
    timestamp:         str           # required
    applied_value:     Any           # required when value-setting
    previous_value:    Any           # required when value-setting
    side_effects:      list[str]     # recommended
    compensation_hint: Optional[str] # required when compensable=True


@dataclass
class DoResponseBuilder:
    """
    Builds a compliant DoResponse from a partial dict returned by
    a @do_tool implementation.
    """
    tool_name:          str
    compensable:        bool
    side_effects:       list[str]
    compensation_hint_template: Optional[str] = None

    def build(
        self,
        raw:              dict,
        idempotency_key:  str,
        call_kwargs:      dict,
        exc:              Optional[Exception] = None,
    ) -> DoResponse:

        if exc is not None:
            return DoResponse(
                status="failed",
                idempotency_key=idempotency_key,
                compensable=self.compensable,
                side_effects=[],
                compensation_hint=None,
                timestamp=_now(),
            )

        from promcp.exceptions import InvalidStatusError
        status = raw.get("status", "success")
        if status not in STATUS_VALUES:
            raise InvalidStatusError(self.tool_name, status)

        # Render compensation_hint template with call kwargs if template given
        hint: Optional[str] = raw.get("compensation_hint")
        if hint is None and self.compensation_hint_template:
            try:
                hint = self.compensation_hint_template.format(**call_kwargs)
            except KeyError:
                hint = self.compensation_hint_template  # unrendered fallback

        if self.compensable and hint is None:
            from promcp.exceptions import ContractViolation
            raise ContractViolation(
                self.tool_name,
                ["compensation_hint"],
                "compensable=True requires compensation_hint in response or "
                "compensation_hint_template in decorator.",
            )

        result: DoResponse = {
            "status":           status,
            "idempotency_key":  idempotency_key,
            "compensable":      self.compensable,
            "side_effects":     raw.get("side_effects", self.side_effects),
            "compensation_hint": hint,
            "timestamp":        raw.get("timestamp", _now()),
        }

        if "applied_value" in raw:
            result["applied_value"] = raw["applied_value"]
        if "previous_value" in raw:
            result["previous_value"] = raw["previous_value"]

        # Pass through any domain extension fields
        for k, v in raw.items():
            if k not in result:
                result[k] = v

        return result


# ─────────────────────────────────────────────────────────────────────────────
# can_do response — CapabilityReport
# ─────────────────────────────────────────────────────────────────────────────

class Candidate(TypedDict, total=False):
    capability:          str        # required
    source:              str        # required
    confidence:          float      # required
    permission:          Permission # required
    valid_until:         str        # required — ISO 8601
    current_state:       dict       # recommended
    constraints:         dict       # recommended
    side_effects:        list[str]  # recommended
    estimated_latency_ms: int       # optional


class BlockedEntry(TypedDict, total=False):
    capability: str        # required
    source:     str        # required
    permission: Permission # required
    reason:     str        # required
    details:    Optional[str]


class CapabilityReport(TypedDict, total=False):
    query_id:   str              # required
    feasible:   bool             # required — auto-calculated
    candidates: list[Candidate]  # required
    blocked:    list[BlockedEntry]  # required
    context:    dict             # recommended
    metadata:   dict             # recommended


@dataclass
class CanDoResponseBuilder:
    """
    Builds a compliant CapabilityReport from a partial dict returned by
    a @can_do_tool implementation.

    Auto-calculates:
      - query_id  (UUIDv4 if not provided)
      - feasible  (true iff any candidate has permission: "allowed")
      - metadata.timestamp
      - metadata.total_latency_ms
    """
    tool_name: str

    def build(
        self,
        raw:            dict,
        latency_ms:     int,
        exc:            Optional[Exception] = None,
    ) -> CapabilityReport:
        import uuid

        if exc is not None:
            return CapabilityReport(
                query_id=str(uuid.uuid4()),
                feasible=False,
                candidates=[],
                blocked=[{
                    "capability": "unknown",
                    "source":     self.tool_name,
                    "permission": "source_unreachable",
                    "reason":     str(exc),
                }],
                context={},
                metadata={"timestamp": _now(), "total_latency_ms": latency_ms},
            )

        candidates: list[Candidate] = raw.get("candidates", [])
        blocked:    list[BlockedEntry] = raw.get("blocked", [])

        from promcp.exceptions import ContractViolation
        for i, candidate in enumerate(candidates):
            if "valid_until" not in candidate:
                raise ContractViolation(
                    self.tool_name,
                    ["valid_until"],
                    f"candidates[{i}] is missing required field 'valid_until'. "
                    "Every candidate must declare when its precondition snapshot expires.",
                )

        # Auto-calculate feasible
        feasible = any(
            c.get("permission") == "allowed"
            for c in candidates
        )

        result: CapabilityReport = {
            "query_id":   raw.get("query_id", str(uuid.uuid4())),
            "feasible":   feasible,
            "candidates": candidates,
            "blocked":    blocked,
            "context":    raw.get("context", {}),
            "metadata":   {
                "timestamp":        _now(),
                "total_latency_ms": latency_ms,
                **raw.get("metadata", {}),
            },
        }

        # Pass through any domain extension fields
        for k, v in raw.items():
            if k not in result:
                result[k] = v

        return result


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
