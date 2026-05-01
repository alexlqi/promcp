# Changelog

All notable changes to the TMCP specification and tooling will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Specification changes follow: **Major** = incompatible contract changes, **Minor** = backward-compatible additions, **Patch** = clarifications and corrections.

---

## [Unreleased]

- `start_*` + `read_status_*` pattern for async long-running mutations (v0.3 target)
- `stream_*` pattern for continuous observation (v0.4 target)
- Multi-server saga coordination pattern (v0.5 target)
- `tmcp lint` validator CLI

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
