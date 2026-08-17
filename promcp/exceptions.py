"""
proMCP Exceptions
-----------------
All exceptions raised by the promcp package.

Author : @alexlqi (https://github.com/alexlqi)
Org    : EnthalpyDW / GoMethos
"""


class ProMCPError(Exception):
    """Base class for all proMCP errors."""


class ContractViolation(ProMCPError):
    """
    Raised when a tool's response violates its proMCP contract at runtime.
    This is a programming error — the tool implementation returned a dict
    that does not satisfy the required response schema for its category.
    """

    def __init__(self, tool_name: str, missing_fields: list[str], extra: str = ""):
        self.tool_name = tool_name
        self.missing_fields = missing_fields
        msg = (
            f"[proMCP] Contract violation in '{tool_name}': "
            f"missing required fields {missing_fields}."
        )
        if extra:
            msg += f" {extra}"
        super().__init__(msg)


class DecoratorMisuseError(ProMCPError):
    """
    Raised at decoration time (import / startup) when a decorator is used
    incorrectly — wrong prefix, missing idempotency_key parameter, etc.
    Fail-fast: errors surface before the server starts, not at call time.
    """

    def __init__(self, tool_name: str, reason: str):
        self.tool_name = tool_name
        msg = f"[proMCP] Decorator misuse on '{tool_name}': {reason}"
        super().__init__(msg)


class CanDoSingletonError(ProMCPError):
    """
    Raised when a second @can_do_tool is registered in the same registry.
    Exactly one can_do tool is permitted per proMCP-compliant server.
    """

    def __init__(self, existing: str, new: str):
        msg = (
            f"[proMCP] Only one can_do tool is allowed per server. "
            f"Existing: '{existing}', attempted: '{new}'."
        )
        super().__init__(msg)


class InvalidQualityError(ProMCPError):
    """Raised when a read_* tool returns an unknown quality value."""

    VALID = {"good", "stale", "degraded", "error"}

    def __init__(self, tool_name: str, value: str):
        msg = (
            f"[proMCP] '{tool_name}' returned unknown quality '{value}'. "
            f"Allowed: {sorted(self.VALID)}."
        )
        super().__init__(msg)


class InvalidStatusError(ProMCPError):
    """Raised when a do_* tool returns an unknown status value."""

    VALID = {"success", "partial", "failed"}

    def __init__(self, tool_name: str, value: str):
        msg = (
            f"[proMCP] '{tool_name}' returned unknown status '{value}'. "
            f"Allowed: {sorted(self.VALID)}."
        )
        super().__init__(msg)
