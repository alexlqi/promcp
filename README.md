# proMCP — Proactive MCP Convention

**Version 0.2.0 — Working Draft**

> *A semantic verb contract for MCP tool design: `read_*`, `do_*`, `can_do`*

---

## What is proMCP

proMCP is a lightweight semantic convention for designing tools in Model Context Protocol (MCP) servers. It imposes a three-verb contract on every tool exposed to an AI agent or orchestrator, making side effects, preconditions, and state observations explicit at the naming and response level — before any inference occurs.

proMCP does not replace MCP. It is a discipline layered on top of it.

**proMCP is domain-agnostic.** It applies equally to software services, IoT devices, healthcare systems, financial APIs, and any other domain where agents need to interact with stateful systems. Domain-specific extensions — such as [PhysMCP](https://physmcp.org) for physical-world IoT deployments — specialize proMCP for their context without replacing its base contracts.

---

## The Problem

MCP gives agents the ability to call tools. It does not tell agents — or orchestrators — which tools mutate state, which are safe to parallelize, which require preconditions, or how to reason about failure and compensation. That ambiguity is left to descriptions, which are natural language, and to the model, which must infer intent from text.

In production systems this causes five recurring failures:

**Tool selection errors.** Models pick the wrong tool when multiple tools have overlapping descriptions but different side effects. The more tools a server exposes, the worse this degrades.

**Unguarded mutations.** Agents execute write operations without verifying preconditions. The plan and the execution are the same step. There is no dry-run surface.

**Non-parallelizable reads.** Without a semantic signal that a tool is side-effect-free, orchestrators treat all tools as potentially stateful and serialize them unnecessarily, increasing latency and cost.

**Opaque failure modes.** Tool responses mix success, partial success, and failure into untyped text or ad-hoc JSON. Orchestrators cannot reason about compensation, idempotency, or retry strategy without parsing natural language.

**Stale state decisions.** Agents act on observations without knowing how fresh the data is. In fast-changing systems — physical sensors, live markets, health telemetry — stale reads cause incorrect actions.

proMCP resolves all five.

---

## The Triad

Every tool in a proMCP-compliant MCP server belongs to exactly one of three categories, declared by its name prefix.

### `read_*`

**Observation. No side effects.**

Safe to call in parallel. Safe to retry without consequence. Safe to cache within the declared freshness window. Returns data with explicit quality and freshness metadata so the orchestrator knows how much to trust the snapshot.

Examples: `read_temperature_zone3`, `read_inventory_sku_001`, `read_patient_vitals_today`

### `do_*`

**Mutation. Has side effects.**

Must be idempotent — every `do_*` tool accepts or generates an `idempotency_key`. Must declare whether its effects are compensable, and if so, provide a compensation hint. Declares its side effects explicitly so the orchestrator can reason about downstream impact before execution.

Examples: `do_set_fan_speed`, `do_update_inventory`, `do_submit_claim`

### `can_do`

**Precondition. No side effects.**

Answers the question: *is this action allowed and feasible right now, given current state?*

Returns structured candidates (capable tools), blockers (tools that matched semantically but cannot execute), context (relevant current observations), and an expiry signal indicating how long the answer is valid. Enables plan-before-act reasoning without executing anything.

`can_do` is the only generic tool in the triad — it takes a structured intent query rather than a capability-specific name.

---

## Response Contracts

The triad becomes a standard when response shapes are typed. proMCP mandates the following schemas for every tool in its category.

### `read_*` response

```json
{
  "value": "<any>",
  "unit": "string | null",
  "timestamp": "ISO 8601",
  "quality": "good | stale | degraded | error"
}
```

**`quality` semantics:**

| Value | Meaning |
|-------|---------|
| `good` | Value is fresh and from a reliable source |
| `stale` | Value is beyond its declared cache TTL but no fresher data is available |
| `degraded` | Source is available but operating outside normal parameters |
| `error` | Read failed; value is absent or unreliable |

`quality` was introduced in [PhysMCP](https://physmcp.org) for physical sensor semantics and is adopted here as the standard field over the earlier `freshness` enum. It covers the `degraded` state — partial signal, noise, sensor fault — that `freshness` did not model.

### `do_*` response

```json
{
  "status": "success | partial | failed",
  "idempotency_key": "string",
  "applied_value": "<any | null>",
  "previous_value": "<any | null>",
  "side_effects": ["string"],
  "compensable": true,
  "compensation_hint": "string | null",
  "timestamp": "ISO 8601"
}
```

`idempotency_key` is required. `compensable` is required. `compensation_hint` is required when `compensable: true` — it names the tool and value needed to reverse the action. `applied_value` and `previous_value` are required when the operation sets a measurable value; null otherwise.

### `can_do` response — CapabilityReport

```json
{
  "query_id": "uuid-v4",
  "feasible": true,
  "candidates": [
    {
      "capability": "string",
      "source": "string",
      "confidence": 0.92,
      "permission": "allowed",
      "current_state": {
        "value": "<any>",
        "unit": "string | null",
        "timestamp": "ISO 8601"
      },
      "constraints": {
        "min": "<number | null>",
        "max": "<number | null>",
        "unit": "string | null",
        "enum_values": ["string"] 
      },
      "side_effects": ["string"],
      "valid_until": "ISO 8601",
      "estimated_latency_ms": 50
    }
  ],
  "blocked": [
    {
      "capability": "string",
      "source": "string",
      "permission": "policy_denied",
      "reason": "string",
      "details": "string | null"
    }
  ],
  "context": {
    "related_reads": ["string"],
    "current_observations": {}
  },
  "metadata": {
    "timestamp": "ISO 8601",
    "total_latency_ms": 120
  }
}
```

**`permission` enum** (applicable to both `candidates` and `blocked`):

| Value | Meaning |
|-------|---------|
| `allowed` | Action will execute |
| `requires_human_approval` | Human-in-the-loop confirmation required |
| `policy_denied` | Local policy rejects the action |
| `rate_limited` | Rate limit exceeded for this period |
| `cooldown_active` | Cooldown from previous action still active |
| `out_of_range` | Requested value outside declared bounds |
| `permission_insufficient` | Caller lacks required role |
| `source_unreachable` | Tool source is offline or unreachable |
| `partition_no_quorum` | Distributed quorum not met (multi-node deployments) |

**`valid_until`** is a first-class contract field on every candidate. A `can_do` response without `valid_until` on its candidates MUST be treated as a snapshot with zero guaranteed validity window. Orchestrators MUST check `valid_until` before executing a `do_*` derived from a prior `can_do` call.

**`confidence`** is a float 0.0–1.0 representing semantic match strength between the query intent and the capability. A score below 0.7 SHOULD trigger a confirmation step before `do_*` execution.

---

## The Canonical Orchestration Pattern

proMCP defines a four-step execution contract between an orchestrator and a proMCP-compliant server:

```
1. can_do(intent_query)
   → validate preconditions, discover capable tools, check permissions
   → receive candidates with valid_until timestamps

2. read_*(required_state)   [parallelizable]
   → gather all needed observations before committing to action
   → check quality field — do not act on degraded or error reads

3. do_*(action, idempotency_key, payload)
   → execute only if valid_until has not expired
   → execute only against candidates with permission: allowed
   → retain idempotency_key for retry and audit

4. read_*(post_condition_state)
   → verify the world matches the expected post-state
   → if quality: degraded, flag for human review
```

This pattern separates planning from execution, observation from mutation, and intent from effect. It makes agentic loops auditable at every step.

**Step 1 is not optional for mutations with side effects.** Skipping `can_do` before a `do_*` is an anti-pattern in any system where the action is not trivially reversible.

**Step 2 is always parallelizable.** All `read_*` calls in step 2 MAY be fanned out concurrently without coordination.

**Step 4 closes the loop.** An agent that does not verify post-state cannot detect partial success and cannot initiate compensation.

---

## proMCP and Domain Extensions

proMCP is the base specification. Domain-specific deployments extend it by:

- Adding fields to response schemas that are meaningful in the domain
- Specializing `can_do` to include domain routing mechanisms
- Declaring manifest formats that bind capabilities to domain resources

The extension contract is: **a domain extension MUST be a superset of proMCP contracts.** Every field defined by proMCP must be present with the same semantics. Extensions may add fields; they may not remove or redefine existing ones.

**[PhysMCP](https://physmcp.org)** is the reference domain extension for physical-world IoT deployments. It extends proMCP with:

- Declarative device manifests (`physmcp.manifest.yml`) binding semantic capabilities to hardware interfaces (I2C, GPIO, Modbus, RS-485, etc.)
- A peer-to-peer semantic mesh with gossip-based discovery
- A floating coordinator protocol for distributed `can_do` queries
- Device profiles for constrained hardware (Full / Lite / Proxy / Aggregator)
- Physical policy enforcement (`physmcp.policy.yml`) with time windows, quorum requirements, and range guards
- Network partition detection and recovery protocols

Several improvements in proMCP v0.2 were directly derived from the PhysMCP spec: the `quality` field on `read_*`, `valid_until` on `can_do` candidates, `applied_value` and `previous_value` on `do_*`, the `permission` enum, and the `CapabilityReport` structure for `can_do` responses.

---

## Improvements in v0.2 over v0.1

| Area | v0.1 | v0.2 |
|------|------|------|
| `read_*` freshness | `freshness: realtime\|cached\|stale` | `quality: good\|stale\|degraded\|error` |
| `do_*` observable delta | not specified | `applied_value` + `previous_value` |
| `can_do` response | flat `allowed` bool + `blockers[]` | `CapabilityReport` with `candidates[]`, `blocked[]`, `context`, `metadata` |
| `can_do` expiry | `expires_at` on response root | `valid_until` per candidate (staleness is per-capability, not global) |
| `can_do` confidence | not specified | `confidence` float 0.0–1.0 per candidate |
| Permission semantics | not specified | typed `permission` enum with 9 values |
| Side effects | declared on response | declared on response AND on candidate in `can_do` (pre-execution visibility) |
| Distributed deployments | not addressed | `partition_no_quorum` permission value, quorum semantics defined |
| Domain extensions | not addressed | extension contract defined — superset rule |

---

## Anti-Patterns

**Using a `do_*` tool for reads.** If a tool has no side effects it is a `read_*`. Mixing mutation and observation in one tool destroys parallelizability and breaks the orchestrator's planning model.

**Omitting `idempotency_key` from `do_*`.** Without an idempotency key, retry logic is unsafe. Every `do_*` must be retryable without double-execution.

**Skipping `can_do` before irreversible mutations.** For any `do_*` where `compensable: false`, calling `can_do` first is not optional. It is the only opportunity to detect blockers before side effects are committed.

**Acting on a `can_do` response after `valid_until`.** The precondition snapshot is stale. Permissions change. State changes. Re-calling `can_do` is cheap relative to the cost of executing a mutation against an invalid precondition.

**Treating `confidence < 0.7` as confirmed.** Low-confidence candidates mean the semantic match is uncertain. The orchestrator must not silently proceed — it must escalate to human review or request clarification.

**Exposing more than 8 tools per server without grouping.** Tool selection degrades above this threshold. Group tools into domain-specific servers and expose only the relevant subset per agent phase.

---

## Compliance Signal

A proMCP-compliant MCP server:

- Names every tool with exactly one of: `read_`, `do_`, `can_do`
- Returns the typed response schema for its category on every call
- Declares `idempotency_key` in every `do_*` response
- Declares `valid_until` in every candidate within a `can_do` response
- Declares `compensable` in every `do_*` response
- Documents `side_effects` on every `do_*` tool and exposes them in `can_do` candidates before execution

A tool that does not meet these criteria is not proMCP-compliant regardless of its naming.

---

## Roadmap

**v0.3** — Async operations: `start_*` + `read_status_*` pattern for long-running mutations.

**v0.4** — Streaming reads: `stream_*` for continuous observation (telemetry, live feeds).

**v0.5** — Multi-server compensation: saga pattern coordination across proMCP servers.

---

## Validator

```bash
proMCP-lint ./my_server.py

  ✓ read_inventory
  ✓ read_temperature_0
  ✓ do_update_stock
  do_delete_record
    ✗ do_delete_record            [R006] do_* responseSchema missing 'compensable' field.
  can_do
    ✗ can_do                      [R010] can_do candidates[] missing required field: 'valid_until'.

✗ 2 error(s)  0 warnings
```

The validator is available at [github.com/aalinsvid/proMCP](https://github.com/aalinsvid/proMCP).

---

## Status

proMCP v0.2.0 is a working draft. The spec is open for discussion, issues, and pull requests.

**Reference domain extension:** [PhysMCP](https://physmcp.org) — Physical Model Context Protocol for IoT mesh deployments.

---

*proMCP is not affiliated with Anthropic. It is a community convention built on top of the Model Context Protocol.*

*Spec authors: EnthalpyDW / GoMethos*
*License: CC-BY-SA 4.0*
