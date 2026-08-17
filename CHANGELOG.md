# Changelog

All notable changes to the proMCP specification and tooling will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Specification changes follow: **Major** = incompatible contract changes, **Minor** = backward-compatible additions, **Patch** = clarifications and corrections.

---

## [0.5.0] — 2026-08-17

### Tooling — BREAKING

The `tmcp` -> `promcp` package rename (0.4.0 and earlier) never reached the
rest of the leftover "TMCP" naming in code and docstrings. Completing it
renames two pieces of public API:

- **Renamed** `promcp.exceptions.TMCPError` → `ProMCPError`. Every exception
  in `promcp.exceptions` (`ContractViolation`, `DecoratorMisuseError`,
  `CanDoSingletonError`, `InvalidQualityError`, `InvalidStatusError`) now
  subclasses `ProMCPError`. No compatibility alias — `except TMCPError` in
  downstream code must become `except ProMCPError`.
- **Renamed** the introspection attributes `@read_tool`/`@do_tool`/`@can_do_tool`
  attach to decorated functions: `__tmcp_name__` → `__promcp_name__`,
  `__tmcp_category__` → `__promcp_category__`.
- **Fixed** remaining "TMCP" module docstrings, error message text, and
  `github.com/alexlqi/tmcp` links across `promcp/*.py`, `promcp/adapters/*`,
  `promcp/linter/checker.py`, and `examples/*.json` — all now say proMCP /
  `github.com/alexlqi/promcp`.

---

## [0.4.1] — 2026-08-17

### Tooling

- **Fixed** `promcp-lint` crashing with `UnicodeEncodeError` on Windows consoles using a legacy codepage (e.g. cp1252), which can't encode the CLI's `✗ ⚠ ✓ ·` glyphs. stdout/stderr are now reconfigured to UTF-8 when the interpreter supports it.
- **Fixed** `promcp-lint` still identifying itself as `tmcp-lint` / `TMCP v0.2.0` and linking to the old `github.com/alexlqi/tmcp` repo — leftover from the package rename that `promcp/linter/cli.py` was missed by. It now reports the real spec version via `promcp.__spec_version__` and the current repo URL (`github.com/alexlqi/promcp`). The `--json` output key is renamed `tmcp_version` → `promcp_version`.

---

## [0.4.0] — 2026-08-17

### Specification

- **Added** `unroutable[]` to CapabilityReport (§6.3, §7.4). `blocked[]` names a capability, so it cannot express "nothing produces this outcome" — and §12.2 still demands an explanation for `feasible: false`. The reference implementation was papering over the gap with `"capability": "unknown"`.
- **Added** AP-9: `idempotency_key` derived from operation type rather than operation instance. A server obeying §9.2 returns the first operation's result and skips the second one's effect; the caller sees `succeeded`.
- **Added** AP-10: asserting `feasible` instead of deriving it from candidate permissions.
- **Clarified** §9.1 with an explicit rule for derived keys and worked bad/good examples.
- **Fixed** §14.1.3, whose `promcp_base` example was pinned to `0.2.0` after the spec moved to 0.3.0 — extensions copying it literally declared a stale base.

### Tooling

- **Added** `UnroutableEntry` and `CapabilityReport.unroutable` to `promcp.contracts`.
- **Changed** `CanDoResponseBuilder` exception path to report an unreachable source through `unroutable[]` instead of a synthetic `"capability": "unknown"` blocked entry.
- **Added** linter checks `R014` (unroutable entry shape) and `R015` (`unroutable[]` declared without `feasible` being derivable).
- **Fixed** this file describing itself as the changelog of "the TMCP specification", and the `tmcp lint` reference in Unreleased.

---

## [Unreleased]

- `start_*` + `read_status_*` pattern for async long-running mutations (v0.3 target)
- `stream_*` pattern for continuous observation (v0.4 target)
- Multi-server saga coordination pattern (v0.5 target)
- `promcp-lint` validator CLI

---

## [0.3.0] — 2026-07-22

### Fixed (addresses PR #2 review)

- **Transport naming now compliant with ProMCP's own linter:** the adapter
  emitted `can_do__` / `read__` / `do__` (double underscore, and a per-capability
  `can_do__x`), which `promcp/linter/checker.py` rejects. Now emits `read_<cap>`
  / `do_<cap>` and a singleton `can_do`. `register_can_do()` no longer takes a
  capability argument.
- **Added `tests/test_transport.py`:** hermetic tests (FastMCP stubbed) covering
  the emitted names, `check_naming` compliance, the `can_do` singleton, and the
  actionable `ImportError` when `fastmcp` is absent.
- Resolved the stale `>>> ACCIÓN REQUERIDA <<<` note in
  `fastmcp-plan/fastmcp.txt`; corrected the "imported in exactly one file"
  wording (now "one runtime file").

### Tooling

- **FastMCP transport adapter (ADR-001):** FastMCP incorporated as an optional,
  version-pinned transport dependency isolated behind `promcp.transport`
  (`ProMCPServer`, `TriadicSurface`). The triadic convention survives the
  transport crossing using the same names the ProMCP linter enforces:
  `read_<cap>` / `do_<cap>` tools and a singleton `can_do` — so an exported
  server passes ProMCP's own `check_naming`. FastMCP is imported in exactly one
  runtime file (`promcp/transport/fastmcp_adapter.py`); the rest of the package
  imports `promcp.transport`. Install via the extra:
  `pip install 'promcp[transport]'`.
- **Dependency policy:** `transport = ["fastmcp>=3.4,<4"]` — floor 3.4 pulls the
  SSRF/OAuth fixes and the Starlette floor for CVE-2026-48710; ceiling `<4`
  avoids an unintended major. The exact audited pin lives in the lockfile, not
  here. NOT vendored.
- **Apache-2.0 compliance:** added `NOTICE` and
  `THIRD_PARTY_LICENSES/fastmcp.txt` (full license text); wired into the
  distribution via `license-files`.
- **Dependency floors refreshed:** `typing_extensions>=4.12`, `mcp>=1.9`,
  `pyyaml>=6.0.1`, `pytest>=8.2` (dev).

---

## [0.2.0] — 2026-04-30

### Specification

#### Breaking changes from v0.1.0

- **`read_*` response:** field `freshness` (enum `realtime|cached|stale`) replaced by `quality` (enum `good|stale|degraded|error`). The `degraded` value covers sensor faults and partial-signal states that `freshness` could not model. Any v0.1 consumer reading `freshness` must migrate to `quality`.
- **`can_do` response:** flat structure (`allowed: bool`, `blockers: []`, `expires_at`) replaced by the full `CapabilityReport` object. Shape is not backward-compatible.
- **`can_do` expiry:** `expires_at` on the response root replaced by `valid_until` per candidate object. Expiry is now per-capability, not global, because different tools within the same server may have different permission volatility.

#### Additions

- **`do_*` response:** added `applied_value` and `previous_value` fields. Required when the operation sets a measurable value. Enables delta-observable mutations and audit trails without a subsequent `read_*`.
- **`can_do` CapabilityReport:** full structure with `candidates[]`, `blocked[]`, `context`, `metadata`. Derived from the PhysMCP specification (physmcp.org).
- **`candidates[]` fields:** `confidence` (float 0.0–1.0), `valid_until` (ISO 8601), `current_state`, `constraints`, `side_effects`, `estimated_latency_ms`.
- **`blocked[]` fields:** `capability`, `source`, `permission`, `reason`, `details`.
- **`permission` enum:** typed 9-value enum replacing unstructured error strings. Values: `allowed`, `requires_human_approval`, `policy_denied`, `rate_limited`, `cooldown_active`, `out_of_range`, `permission_insufficient`, `source_unreachable`, `partition_no_quorum`.
- **`side_effects` on candidates:** side effects are now visible in the `can_do` response before execution, not only in the `do_*` response after execution.
- **Confidence threshold:** `confidence < 0.7` defined as the threshold requiring human review or clarification before proceeding to `do_*`.
- **Domain extension contract (§14):** superset rule formalized. Extensions must declare `tmcp_base` version. Additional `permission` values must use namespaced prefix.
- **JSON Schema definitions (§7):** four schemas published at `github.com/alexlqi/tmcp/schemas/`: `read-response.json`, `do-response.json`, `can-do-input.json`, `capability-report.json`.
- **Idempotency contract (§9):** client and server responsibilities formalized. Deduplication window defined (minimum 24 hours recommended).
- **Compensation contract (§10):** machine-parseable `compensation_hint` format defined. Orchestrator behavior on cascading failure specified.
- **Staleness and validity contract (§11):** `valid_until` window recommendations by permission volatility category.
- **Tool density guidelines (§13):** recommended ≤8 tools per server, phase-split grouping strategy.
- **Examples (§17):** three full JSON scenarios — happy path, rate-limited blocked, human approval required.

#### Clarifications

- Canonical orchestration pattern (§8): added explicit rules for when each step may be skipped.
- Anti-patterns (§15): expanded from 6 to 8, added AP-7 (generic tool names) and AP-8 (conflating `blocked` with permanent failure).
- Compliance checklist (§16): split into server compliance and orchestrator compliance.

### Attribution

The following changes in v0.2.0 were derived from the [PhysMCP specification](https://physmcp.org) (Physical Model Context Protocol for IoT mesh deployments):

- `quality` field semantics and enum values
- `CapabilityReport` structure (`candidates[]`, `blocked[]`, `context`, `metadata`)
- `valid_until` per-candidate expiry model
- `applied_value` and `previous_value` on `do_*`
- `permission` enum (extended for software domain)

---

## [0.1.0] — 2026-04-30

### Specification

#### Added

- Initial declaration of the triadic verb contract: `read_*`, `do_*`, `can_do`
- Basic response shapes for all three categories
- Canonical four-step orchestration pattern: can_do → read_* → do_* → read_*
- `idempotency_key` requirement on `do_*`
- `compensable` + `compensation_hint` on `do_*`
- `expires_at` on `can_do` response root
- `freshness` enum on `read_*`: `realtime | cached | stale`
- `consistency` field on `read_*`: `strong | eventual`
- Initial anti-patterns (6)
- Compliance signal checklist
- Domain extension concept (superset rule, not yet formalized)

---

## Version history summary

| Version | Date | Type | Key change |
|---------|------|------|-----------|
| 0.2.0 | 2026-04-30 | Minor (breaking) | CapabilityReport, quality, valid_until per candidate, permission enum |
| 0.1.0 | 2026-04-30 | Initial | Triadic contract declaration |

---

*Author: [@alexlqi](https://github.com/alexlqi)*
*Organizations: EnthalpyDW / GoMethos*
*Repository: [github.com/alexlqi/tmcp](https://github.com/alexlqi/tmcp)*
