"""
proMCP Registry
-----------------
Central registry for all tools decorated with @read_tool, @do_tool,
and @can_do_tool. Each registry instance is independent — supports
multiple servers in the same process.

The default registry is a module-level singleton for convenience.
Pass an explicit Registry() instance to decorators for multi-server setups.

Author : @alexlqi (https://github.com/alexlqi)
Org    : EnthalpyDW / GoMethos
Spec   : https://github.com/alexlqi/promcp
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

from promcp.exceptions import CanDoSingletonError


ToolCategory = Literal["read", "do", "can_do"]


@dataclass
class ToolEntry:
    """Metadata for a single registered proMCP tool."""
    name:        str
    category:    ToolCategory
    fn:          Callable
    description: str

    # read_* metadata
    unit:        Optional[str]       = None

    # do_* metadata
    compensable: bool                = False
    side_effects: list[str]          = field(default_factory=list)
    compensation_hint_template: Optional[str] = None

    # Derived input schema (populated by decorators)
    input_schema: dict               = field(default_factory=dict)

    def to_dict(self) -> dict:
        """
        Serialize to a raw tool definition dict compatible with promcp-lint
        and the raw adapter. Includes responseSchema inferred from category.
        """
        base = {
            "name":        self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }

        if self.category == "read":
            base["responseSchema"] = {
                "type": "object",
                "properties": {
                    "value":     {},
                    "unit":      {"type": ["string", "null"]},
                    "timestamp": {"type": "string", "format": "date-time"},
                    "quality":   {
                        "type": "string",
                        "enum": ["good", "stale", "degraded", "error"],
                    },
                },
            }

        elif self.category == "do":
            base["responseSchema"] = {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["success", "partial", "failed"],
                    },
                    "idempotency_key":   {"type": "string"},
                    "applied_value":     {},
                    "previous_value":    {},
                    "side_effects":      {"type": "array", "items": {"type": "string"}},
                    "compensable":       {"type": "boolean"},
                    "compensation_hint": {"type": ["string", "null"]},
                    "timestamp":         {"type": "string", "format": "date-time"},
                },
            }

        elif self.category == "can_do":
            base["responseSchema"] = {
                "type": "object",
                "properties": {
                    "query_id": {"type": "string", "format": "uuid"},
                    "feasible": {"type": "boolean"},
                    "candidates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "capability":  {"type": "string"},
                                "source":      {"type": "string"},
                                "confidence":  {"type": "number"},
                                "permission":  {
                                    "type": "string",
                                    "enum": [
                                        "allowed", "requires_human_approval",
                                        "policy_denied", "rate_limited",
                                        "cooldown_active", "out_of_range",
                                        "permission_insufficient",
                                        "source_unreachable", "partition_no_quorum",
                                    ],
                                },
                                "valid_until": {"type": "string", "format": "date-time"},
                            },
                        },
                    },
                    "blocked": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "capability": {"type": "string"},
                                "source":     {"type": "string"},
                                "permission": {"type": "string"},
                                "reason":     {"type": "string"},
                            },
                        },
                    },
                    # §6.3 — no hay capacidad que nombrar cuando nada produce el
                    # resultado pedido, así que `unroutable[]` no lleva
                    # `capability`: lleva el outcome que no se pudo alcanzar.
                    "unroutable": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "outcome": {"type": "string"},
                                "reason":  {
                                    "type": "string",
                                    "enum": [
                                        "no_producer",
                                        "requirements_unmet",
                                        "malformed_request",
                                    ],
                                },
                                "detail":  {"type": "string"},
                                "producers_found": {
                                    "type": "array", "items": {"type": "string"},
                                },
                                "missing_requirements": {
                                    "type": "array", "items": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            }

        return base


class Registry:
    """
    Holds all ToolEntry objects for a single proMCP server instance.
    Thread-safe for reads; decoration happens at import time (single-threaded).
    """

    def __init__(self, name: str = "default"):
        self.name = name
        self._tools:  dict[str, ToolEntry] = {}
        self._can_do: Optional[str]        = None   # singleton guard

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, entry: ToolEntry) -> None:
        if entry.category == "can_do":
            if self._can_do is not None:
                raise CanDoSingletonError(self._can_do, entry.name)
            self._can_do = entry.name

        self._tools[entry.name] = entry

    # ── Queries ───────────────────────────────────────────────────────────────

    def get(self, name: str) -> Optional[ToolEntry]:
        return self._tools.get(name)

    def all(self) -> list[ToolEntry]:
        return list(self._tools.values())

    def by_category(self, category: ToolCategory) -> list[ToolEntry]:
        return [t for t in self._tools.values() if t.category == category]

    def to_list(self) -> list[dict]:
        """Export all tools as raw dicts — for promcp-lint and adapters."""
        return [e.to_dict() for e in self._tools.values()]

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        return f"Registry(name={self.name!r}, tools={list(self._tools.keys())})"


# Module-level default registry — convenience for single-server setups
default_registry = Registry(name="default")
