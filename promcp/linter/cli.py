"""
promcp-lint CLI
----------------
Entry point for the promcp-lint command.

Author : @alexlqi (https://github.com/alexlqi)
Org    : EnthalpyDW / GoMethos
Spec   : https://github.com/alexlqi/promcp
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

from promcp import __spec_version__
from promcp.linter.checker import (
    Finding,
    LintResult,
    Severity,
    lint_registry,
    lint_server,
)

# Windows consoles default to a legacy codepage (e.g. cp1252) that can't
# encode the ✗/⚠/✓/· glyphs below, crashing the CLI with UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Loader
# ─────────────────────────────────────────────────────────────────────────────

def load_tools(path: str) -> list[dict]:
    if not os.path.exists(path):
        _err(f"File not found: {path}")
        sys.exit(2)

    ext = os.path.splitext(path)[1].lower()

    if ext == ".json":
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "tools" in data:
            return data["tools"]
        _err("JSON must be an array of tool objects or {\"tools\": [...]}")
        sys.exit(2)

    if ext in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            _err("PyYAML not installed. Run: pip install pyyaml")
            sys.exit(2)
        with open(path) as f:
            data = yaml.safe_load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "tools" in data:
            return data["tools"]
        _err("YAML must be a list of tool objects or {tools: [...]}")
        sys.exit(2)

    if ext == ".py":
        spec = importlib.util.spec_from_file_location("_promcp_target", path)
        mod  = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as e:
            _err(f"Could not import {path}: {e}")
            sys.exit(2)

        # Priority 1: decorated registry
        from promcp.registry import Registry
        for attr in vars(mod).values():
            if isinstance(attr, Registry):
                return attr.to_list()

        # Priority 2: promcp.registry.default_registry populated by decorators
        try:
            from promcp.registry import default_registry
            if len(default_registry) > 0:
                return default_registry.to_list()
        except Exception:
            pass

        # Priority 3: TOOLS list or get_tools()
        if hasattr(mod, "TOOLS") and isinstance(mod.TOOLS, list):
            return mod.TOOLS
        for fn_name in ("get_tools", "tools", "list_tools"):
            if hasattr(mod, fn_name) and callable(getattr(mod, fn_name)):
                result = getattr(mod, fn_name)()
                if isinstance(result, list):
                    return result

        _err(f"No Registry, TOOLS list, or get_tools() found in {path}")
        sys.exit(2)

    _err(f"Unsupported file type: {ext}. Supported: .py .json .yaml .yml")
    sys.exit(2)


# ─────────────────────────────────────────────────────────────────────────────
# Output formatters
# ─────────────────────────────────────────────────────────────────────────────

def _err(msg: str) -> None:
    print(f"\033[91m✗ {msg}\033[0m")


def print_human(
    tool_results:    list[LintResult],
    server_findings: list[Finding],
    strict:          bool,
    path:            str,
) -> int:
    BOLD  = "\033[1m"
    RESET = "\033[0m"
    GREEN = "\033[92m"
    RED   = "\033[91m"
    AMBER = "\033[93m"
    BLUE  = "\033[94m"

    SEV_ICON  = {Severity.ERROR: "✗", Severity.WARNING: "⚠", Severity.INFO: "·"}
    SEV_COLOR = {Severity.ERROR: RED, Severity.WARNING: AMBER, Severity.INFO: BLUE}

    errors = warnings = info = 0

    print(f"\n{BOLD}promcp-lint{RESET}  proMCP v{__spec_version__} — {path}\n")

    if server_findings:
        print(f"{BOLD}Server{RESET}")
        for f in server_findings:
            c = SEV_COLOR[f.severity]
            print(f"  {c}{SEV_ICON[f.severity]}{RESET} {'server':<35} [{f.code}] {f.message}")
            if f.severity == Severity.ERROR:   errors   += 1
            if f.severity == Severity.WARNING: warnings += 1
        print()

    for result in tool_results:
        relevant = [f for f in result.findings
                    if f.severity in (Severity.ERROR, Severity.WARNING, Severity.INFO)]
        if not relevant:
            print(f"  {GREEN}✓{RESET} {result.tool}")
            continue

        has_err  = any(f.severity == Severity.ERROR for f in relevant)
        hdr_color = RED if has_err else AMBER
        print(f"  {hdr_color}{result.tool}{RESET}")
        for f in relevant:
            c = SEV_COLOR[f.severity]
            print(f"    {c}{SEV_ICON[f.severity]}{RESET} {f.tool:<33} [{f.code}] {f.message}")
            if f.severity == Severity.ERROR:   errors   += 1
            if f.severity == Severity.WARNING: warnings += 1
            if f.severity == Severity.INFO:    info     += 1

    exit_code = 0
    print()

    err_str  = f"{RED}{BOLD}✗ {errors} error(s){RESET}"   if errors   else f"{GREEN}{BOLD}✓ 0 errors{RESET}"
    warn_str = f"{(RED if strict else AMBER)}{warnings} warning(s){RESET}" if warnings else f"{GREEN}0 warnings{RESET}"
    info_str = f"{BLUE}{info} info{RESET}"                if info     else ""

    parts = [err_str, warn_str] + ([info_str] if info_str else [])
    print("  " + "  ".join(parts))

    if errors or (strict and warnings):
        exit_code = 1

    print(f"\n  Spec : https://github.com/alexlqi/promcp")
    print(f"  Author: @alexlqi\n")
    return exit_code


def print_json_output(
    tool_results:    list[LintResult],
    server_findings: list[Finding],
    strict:          bool,
) -> int:
    all_findings = server_findings + [f for r in tool_results for f in r.findings]
    has_errors   = any(f.severity == Severity.ERROR   for f in all_findings)
    has_warnings = any(f.severity == Severity.WARNING for f in all_findings)

    output = {
        "promcp_version": __spec_version__,
        "server":       [f.to_dict() for f in server_findings],
        "tools":        [r.to_dict() for r in tool_results],
        "summary": {
            "errors":   sum(1 for f in all_findings if f.severity == Severity.ERROR),
            "warnings": sum(1 for f in all_findings if f.severity == Severity.WARNING),
            "info":     sum(1 for f in all_findings if f.severity == Severity.INFO),
            "pass":     not has_errors and (not has_warnings or not strict),
        },
    }
    print(json.dumps(output, indent=2))
    return 0 if output["summary"]["pass"] else 1


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="promcp-lint",
        description=f"Validate MCP server tool definitions against proMCP v{__spec_version__}.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  promcp-lint tools.json
  promcp-lint my_server.py --strict
  promcp-lint tools.yaml --json
  promcp-lint my_server.py --strict --json

Author : @alexlqi (https://github.com/alexlqi)
Spec   : https://github.com/alexlqi/promcp
        """,
    )
    parser.add_argument("file", help="Path to server file (.py, .json, .yaml)")
    parser.add_argument("--strict", action="store_true",
                        help="Treat SHOULD/RECOMMENDED warnings as errors")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")

    args  = parser.parse_args()
    tools = load_tools(args.file)

    if not tools:
        _err(f"No tools found in {args.file}")
        sys.exit(2)

    tool_results, server_findings = lint_server(tools)

    if args.json:
        exit_code = print_json_output(tool_results, server_findings, args.strict)
    else:
        exit_code = print_human(tool_results, server_findings, args.strict, args.file)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
