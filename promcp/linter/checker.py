"""
proMCP Lint Checker
---------------------
All check functions. Decoupled from the CLI so they can be used
programmatically — in tests, CI pipelines, or from a Registry directly.

Author : @alexlqi (https://github.com/alexlqi)
Org    : EnthalpyDW / GoMethos
Spec   : https://github.com/alexlqi/promcp
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from promcp.contracts import (
    PERMISSION_VALUES,
    QUALITY_VALUES,
    STATUS_VALUES,
)


# ─────────────────────────────────────────────────────────────────────────────
# Result model
# ─────────────────────────────────────────────────────────────────────────────

class Severity(Enum):
    ERROR   = "error"
    WARNING = "warning"
    INFO    = "info"


@dataclass
class Finding:
    severity: Severity
    tool:     str
    code:     str
    message:  str

    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "code":     self.code,
            "message":  self.message,
        }


@dataclass
class LintResult:
    tool:     str
    findings: list[Finding] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(f.severity == Severity.ERROR for f in self.findings)

    @property
    def has_warnings(self) -> bool:
        return any(f.severity == Severity.WARNING for f in self.findings)

    def to_dict(self) -> dict:
        return {
            "name":     self.tool,
            "findings": [f.to_dict() for f in self.findings],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

VALID_PREFIXES       = ("read_", "do_")
EXACT_GENERIC        = "can_do"
NAMING_RE            = re.compile(r'^[a-z][a-z0-9_]*$')
MAX_TOOLS_PER_SERVER = 8
REQUIRED_READ        = {"value", "timestamp", "quality"}
REQUIRED_DO          = {"status", "idempotency_key", "compensable", "timestamp"}
REQUIRED_CAN_DO      = {"query_id", "feasible", "candidates", "blocked"}
REQUIRED_CANDIDATE   = {"capability", "source", "confidence", "permission", "valid_until"}
REQUIRED_BLOCKED     = {"capability", "source", "permission", "reason"}
REQUIRED_UNROUTABLE  = {"outcome", "reason", "detail"}
UNROUTABLE_REASONS   = {"no_producer", "requirements_unmet", "malformed_request"}

GENERIC_NAMES = {
    "do_action", "do_update", "do_create", "do_delete",
    "read_data", "read_value", "read_info", "do_execute", "do_run",
}
MUTATION_KEYWORDS = {
    "create", "update", "delete", "set", "reset",
    "trigger", "send", "write", "insert", "modify",
}


# ─────────────────────────────────────────────────────────────────────────────
# Tool-level checks
# ─────────────────────────────────────────────────────────────────────────────

def check_naming(tool: dict) -> list[Finding]:
    findings = []
    name = tool.get("name", "")

    if not name:
        findings.append(Finding(Severity.ERROR, "(unnamed)", "N001",
            "Tool has no 'name' field."))
        return findings

    if name == EXACT_GENERIC:
        return findings

    if not NAMING_RE.match(name):
        findings.append(Finding(Severity.ERROR, name, "N002",
            f"Name must be lowercase_snake_case. Got: '{name}'."))

    if not any(name.startswith(p) for p in VALID_PREFIXES):
        findings.append(Finding(Severity.ERROR, name, "N003",
            "Name must start with 'read_' or 'do_', or be exactly 'can_do'."))

    if name.startswith("read_") and name == "read_":
        findings.append(Finding(Severity.ERROR, name, "N004",
            "read_* tool name must have a capability identifier after the prefix."))

    if name.startswith("do_") and name == "do_":
        findings.append(Finding(Severity.ERROR, name, "N005",
            "do_* tool name must have a capability identifier after the prefix."))

    if len(name) > 64:
        findings.append(Finding(Severity.WARNING, name, "N006",
            f"Tool name exceeds 64 characters ({len(name)}). Consider shortening."))

    if name in GENERIC_NAMES:
        findings.append(Finding(Severity.WARNING, name, "N007",
            f"'{name}' is a generic name. Use a domain-specific capability name."))

    return findings


def check_description(tool: dict) -> list[Finding]:
    findings = []
    name = tool.get("name", "(unnamed)")
    desc = tool.get("description", "")

    if not desc:
        findings.append(Finding(Severity.WARNING, name, "D001",
            "Tool has no description. Descriptions are critical for accurate tool selection."))
        return findings

    if len(desc) < 20:
        findings.append(Finding(Severity.WARNING, name, "D002",
            f"Description is very short ({len(desc)} chars). "
            "Include what the tool does and when NOT to use it."))

    if name.startswith("read_"):
        found = [w for w in MUTATION_KEYWORDS if w in desc.lower()]
        if found:
            findings.append(Finding(Severity.WARNING, name, "D003",
                f"Description of read_* contains mutation keywords: {found}. "
                "Verify this tool has no side effects."))

    return findings


def check_input_schema(tool: dict) -> list[Finding]:
    findings = []
    name   = tool.get("name", "(unnamed)")
    schema = tool.get("inputSchema", {})
    props  = schema.get("properties", {})

    if name == EXACT_GENERIC:
        if "intent" not in props:
            findings.append(Finding(Severity.ERROR, name, "I001",
                "can_do inputSchema must include 'intent' property."))
        else:
            intent_schema = props["intent"]
            intent_type   = intent_schema.get("type", "")
            intent_props  = intent_schema.get("properties", {})
            # If intent is typed as plain 'object' with no properties declared,
            # the decorator used dict annotation — accept it, semantic_tags
            # is enforced at runtime by the decorator.
            if intent_type == "object" and not intent_props:
                pass  # dict annotation — runtime-enforced
            elif "semantic_tags" not in intent_props:
                findings.append(Finding(Severity.ERROR, name, "I002",
                    "can_do intent must include 'semantic_tags' array."))
        return findings

    if name.startswith("do_") and "idempotency_key" not in props:
        findings.append(Finding(Severity.ERROR, name, "I003",
            "do_* inputSchema must include 'idempotency_key' parameter."))

    return findings


def check_response_schema(tool: dict) -> list[Finding]:
    findings = []
    name = tool.get("name", "(unnamed)")
    rs   = tool.get("responseSchema") or tool.get("response_schema")

    if rs is None:
        findings.append(Finding(Severity.INFO, name, "R000",
            "No responseSchema declared. Add 'responseSchema' to enable "
            "full response contract validation."))
        return findings

    props = rs.get("properties", {})

    if name.startswith("read_"):
        for f in REQUIRED_READ - set(props.keys()):
            findings.append(Finding(Severity.ERROR, name, "R001",
                f"read_* responseSchema missing required field: '{f}'. "
                f"Required: {sorted(REQUIRED_READ)}."))

        if "quality" in props:
            q_enum  = set(props["quality"].get("enum", []))
            invalid = q_enum - QUALITY_VALUES
            missing = QUALITY_VALUES - q_enum
            if invalid:
                findings.append(Finding(Severity.ERROR, name, "R002",
                    f"quality enum has invalid values: {invalid}."))
            if missing:
                findings.append(Finding(Severity.ERROR, name, "R003",
                    f"quality enum is incomplete. Missing: {sorted(missing)}."))

    elif name.startswith("do_"):
        for f in REQUIRED_DO - set(props.keys()):
            findings.append(Finding(Severity.ERROR, name, "R004",
                f"do_* responseSchema missing required field: '{f}'. "
                f"Required: {sorted(REQUIRED_DO)}."))

        if "status" in props:
            s_enum  = set(props["status"].get("enum", []))
            invalid = s_enum - STATUS_VALUES
            if invalid:
                findings.append(Finding(Severity.ERROR, name, "R005",
                    f"status enum has invalid values: {invalid}."))

        if "compensable" not in props:
            findings.append(Finding(Severity.ERROR, name, "R006",
                "do_* responseSchema missing 'compensable' field."))

        if "idempotency_key" not in props:
            findings.append(Finding(Severity.ERROR, name, "R007",
                "do_* responseSchema missing 'idempotency_key' field."))

        if "side_effects" not in props:
            findings.append(Finding(Severity.WARNING, name, "R008",
                "do_* responseSchema missing 'side_effects' array (recommended)."))

    elif name == EXACT_GENERIC:
        for f in REQUIRED_CAN_DO - set(props.keys()):
            findings.append(Finding(Severity.ERROR, name, "R009",
                f"can_do responseSchema missing required field: '{f}'. "
                f"Required: {sorted(REQUIRED_CAN_DO)}."))

        if "candidates" in props:
            item_props = props["candidates"].get("items", {}).get("properties", {})
            for f in REQUIRED_CANDIDATE - set(item_props.keys()):
                findings.append(Finding(Severity.ERROR, name, "R010",
                    f"can_do candidates[] missing required field: '{f}'."))
            if "permission" in item_props:
                p_enum  = set(item_props["permission"].get("enum", []))
                invalid = p_enum - PERMISSION_VALUES
                if invalid:
                    findings.append(Finding(Severity.ERROR, name, "R012",
                        f"can_do candidates permission enum has unknown values: {invalid}. "
                        "Use namespaced prefix for domain extensions."))

        if "blocked" in props:
            item_props = props["blocked"].get("items", {}).get("properties", {})
            for f in REQUIRED_BLOCKED - set(item_props.keys()):
                findings.append(Finding(Severity.ERROR, name, "R013",
                    f"can_do blocked[] missing required field: '{f}'."))

        # §6.3 — unroutable[]. Not required, but if it is declared it must be right:
        # a malformed unroutable entry is an unexplained refusal wearing a schema.
        if "unroutable" in props:
            item_props = props["unroutable"].get("items", {}).get("properties", {})
            for f in REQUIRED_UNROUTABLE - set(item_props.keys()):
                findings.append(Finding(Severity.ERROR, name, "R014",
                    f"can_do unroutable[] missing required field: '{f}'. "
                    f"Required: {sorted(REQUIRED_UNROUTABLE)} (spec §6.3)."))
            if "reason" in item_props:
                r_enum  = set(item_props["reason"].get("enum", []))
                invalid = r_enum - UNROUTABLE_REASONS
                if invalid:
                    findings.append(Finding(Severity.ERROR, name, "R014",
                        f"can_do unroutable[].reason enum has unknown values: {sorted(invalid)}. "
                        f"Allowed: {sorted(UNROUTABLE_REASONS)} (spec §6.3)."))
        else:
            findings.append(Finding(Severity.INFO, name, "R015",
                "can_do responseSchema declares no 'unroutable[]'. Without it, a request "
                "whose outcome no capability produces has to be reported either by "
                "inventing a capability name in blocked[] or by an unexplained "
                "feasible: false (spec §6.3)."))

    return findings


def check_side_effects_consistency(tool: dict) -> list[Finding]:
    findings = []
    name = tool.get("name", "(unnamed)")
    if not name.startswith("read_"):
        return findings

    rs    = tool.get("responseSchema") or tool.get("response_schema") or {}
    props = rs.get("properties", {})

    if "side_effects" in props:
        findings.append(Finding(Severity.ERROR, name, "SE001",
            "read_* tool declares 'side_effects'. Read tools must have no "
            "side effects — rename to do_* if mutation occurs."))

    return findings


# ─────────────────────────────────────────────────────────────────────────────
# Server-level checks
# ─────────────────────────────────────────────────────────────────────────────

def check_server_level(tools: list[dict]) -> list[Finding]:
    findings = []
    names    = [t.get("name", "") for t in tools]

    can_do_count = names.count(EXACT_GENERIC)
    if can_do_count == 0:
        findings.append(Finding(Severity.ERROR, "server", "S001",
            "No 'can_do' tool found. Every proMCP-compliant server must expose exactly one."))
    elif can_do_count > 1:
        findings.append(Finding(Severity.ERROR, "server", "S002",
            f"Found {can_do_count} 'can_do' tools. Exactly one is permitted."))

    seen = set()
    for n in names:
        if n in seen:
            findings.append(Finding(Severity.ERROR, "server", "S003",
                f"Duplicate tool name: '{n}'."))
        seen.add(n)

    total = len(tools)
    if total > MAX_TOOLS_PER_SERVER:
        findings.append(Finding(Severity.WARNING, "server", "S004",
            f"{total} tools exceeds recommended maximum of {MAX_TOOLS_PER_SERVER}. "
            "Consider splitting by domain or workflow phase."))

    do_count = sum(1 for n in names if n.startswith("do_"))
    if do_count > 5:
        findings.append(Finding(Severity.WARNING, "server", "S005",
            f"{do_count} do_* tools. Recommended maximum is 5."))

    return findings


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def lint_tool(tool: dict) -> LintResult:
    name   = tool.get("name", "(unnamed)")
    result = LintResult(tool=name)
    result.findings.extend(check_naming(tool))
    result.findings.extend(check_description(tool))
    result.findings.extend(check_input_schema(tool))
    result.findings.extend(check_response_schema(tool))
    result.findings.extend(check_side_effects_consistency(tool))
    return result


def lint_server(tools: list[dict]) -> tuple[list[LintResult], list[Finding]]:
    return [lint_tool(t) for t in tools], check_server_level(tools)


def lint_registry(registry) -> tuple[list[LintResult], list[Finding]]:
    """
    Lint directly from a proMCP Registry instance.
    No file loading needed — tools decorated with @read_tool et al.
    already have full responseSchema attached.
    """
    return lint_server(registry.to_list())
