# proMCP Specification

**Proactive MCP Convention — Formal Specification**
**Version: 0.3.0**
**Status: Working Draft**
**Author: [@alexlqi](https://github.com/alexlqi) — EnthalpyDW / GoMethos**
**License: CC-BY-SA 4.0**

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Terminology](#2-terminology)
3. [Conformance](#3-conformance)
4. [The Three-Verb Contract](#4-the-triadic-verb-contract)
5. [Tool Naming Rules](#5-tool-naming-rules)
6. [Response Schemas](#6-response-schemas)
7. [JSON Schema Definitions](#7-json-schema-definitions)
8. [The Canonical Orchestration Pattern](#8-the-canonical-orchestration-pattern)
9. [Idempotency Contract](#9-idempotency-contract)
10. [Compensation Contract](#10-compensation-contract)
11. [Staleness and Validity Contract](#11-staleness-and-validity-contract)
12. [Permission Model](#12-permission-model)
13. [Tool Density Guidelines](#13-tool-density-guidelines)
14. [Domain Extension Contract](#14-domain-extension-contract)
15. [Anti-Patterns](#15-anti-patterns)
16. [Compliance Checklist](#16-compliance-checklist)
17. [Examples](#17-examples)
18. [Changelog](#18-changelog)

---

## 1. Introduction

proMCP (Proactive MCP Convention) is a semantic discipline for designing tools in Model Context Protocol (MCP) servers. It defines three and only three verb prefixes for tool names — `read_`, `do_`, `can_do` — and mandates typed response contracts for each category.

proMCP does not extend the MCP wire protocol. It does not introduce new transport mechanisms. It operates entirely at the tool naming and response schema layer, making it adoptable in any existing MCP implementation without infrastructure changes.

The goals of proMCP are:

1. Eliminate ambiguity about side effects at the tool selection layer
2. Enable safe parallelization of observation operations
3. Provide a plan-before-act primitive as a first-class protocol concept
4. Mandate typed failure and compensation metadata
5. Make staleness explicit on every observation

proMCP is domain-agnostic. Domain-specific extensions (see §14) specialize it without replacing it.

---

## 2. Terminology

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT, RECOMMENDED, MAY, and OPTIONAL in this document are to be interpreted as described in RFC 2119.

| Term | Definition |
|------|-----------|
| **Tool** | An MCP-callable function exposed by an MCP server |
| **Server** | An MCP server exposing one or more tools |
| **Client** | An MCP client consuming tools — typically an AI agent or orchestrator |
| **Orchestrator** | A client that coordinates multiple tool calls, possibly across multiple servers |
| **Capability** | A named tool in a proMCP-compliant server |
| **Intent query** | The structured input to `can_do` describing a desired action |
| **CapabilityReport** | The structured response of `can_do` |
| **Candidate** | A tool returned by `can_do` as feasible for an intent |
| **Idempotency key** | A unique string identifying a specific execution of a `do_*` operation |
| **Compensation** | The act of reversing a `do_*` side effect via a subsequent tool call |
| **Quality** | The freshness and reliability state of a `read_*` observation |

---

## 3. Conformance

A proMCP-compliant MCP server MUST satisfy all REQUIRED constraints in this specification.

A proMCP-compliant MCP server SHOULD satisfy all RECOMMENDED constraints.

A proMCP-compliant MCP server MAY satisfy OPTIONAL constraints.

Partial conformance is not conformance. A server that names tools correctly but omits required response fields is not proMCP-compliant.

Domain extensions (§14) that are supersets of proMCP are considered proMCP-compliant for the base contract.

---

## 4. The Three-Verb Contract

proMCP defines exactly three tool categories. Every tool MUST belong to exactly one.

### 4.1 `read_*` — Observation

A `read_*` tool observes state. It MUST NOT produce side effects observable outside the tool call itself. It MUST be safe to call multiple times with identical parameters and produce equivalent results within the same quality window.

Properties that MUST hold for every `read_*` tool:

- **No side effects.** The call changes no external state.
- **Parallelizable.** Multiple `read_*` calls MAY execute concurrently without coordination.
- **Retryable.** A failed `read_*` call MAY be retried unconditionally.
- **Quality-declared.** The response MUST include a `quality` field.

### 4.2 `do_*` — Mutation

A `do_*` tool mutates state. It MUST declare its side effects. It MUST be idempotent when called with the same `idempotency_key`. It MUST declare whether its effects are compensable.

Properties that MUST hold for every `do_*` tool:

- **Side effects declared.** The response MUST list `side_effects`.
- **Idempotent by key.** Repeated calls with the same `idempotency_key` MUST produce the same outcome and MUST NOT double-apply the effect.
- **Compensation declared.** The response MUST include `compensable` (boolean).
- **Delta observable.** When the operation sets a measurable value, the response MUST include `applied_value` and `previous_value`.

### 4.3 `can_do` — Precondition

`can_do` is the single generic tool in the triad. It MUST NOT produce side effects. It answers the question: *is this action allowed and feasible right now?*

`can_do` takes a structured intent query and returns a CapabilityReport: a ranked list of capable tools with permission status, current state, constraints, expiry, and context. It is the dry-run surface for the entire server.

There MUST be exactly one `can_do` tool per proMCP-compliant server.

Properties that MUST hold for `can_do`:

- **No side effects.** The call changes no external state.
- **Expiry-declared.** Every candidate in the response MUST include `valid_until`.
- **Permission-typed.** Every candidate and every blocked entry MUST include a `permission` value from the defined enum.
- **Confidence-scored.** Every candidate MUST include a `confidence` float.

---

## 5. Tool Naming Rules

### 5.1 Naming conventions

| Rule | Requirement |
|------|-------------|
| Case | MUST be `lowercase_snake_case` |
| Prefix | MUST start with `read_`, `do_`, or be exactly `can_do` |
| Specificity | SHOULD name the capability, not the implementation |
| Uniqueness | MUST be unique within a server |
| Length | SHOULD NOT exceed 64 characters |

### 5.2 Valid examples

```
read_temperature_zone3
read_inventory_sku_001
read_patient_vitals_today
read_account_balance
do_set_fan_speed
do_update_inventory
do_submit_claim
do_close_valve_main
can_do
```

### 5.3 Invalid examples

```
getTemperature          ← not prefixed
READ_TEMPERATURE        ← not lowercase
do_read_and_update      ← ambiguous — read and write in one tool
set_fan_speed           ← missing prefix
temperature_read        ← prefix must be first
can_do_fan              ← can_do must be singular and generic
```

### 5.4 Prohibited patterns

A tool MUST NOT use a `read_` prefix if it produces side effects.
A tool MUST NOT use a `do_` prefix if it produces no side effects.
A `can_do` tool MUST NOT be named anything other than `can_do`.

---

## 6. Response Schemas

### 6.1 `read_*` response

REQUIRED fields:

```json
{
  "value": "<any>",
  "timestamp": "ISO 8601"
}
```

REQUIRED field with constrained values:

```json
{
  "quality": "good | stale | degraded | error"
}
```

OPTIONAL fields:

```json
{
  "unit": "string"
}
```

**`quality` semantics:**

| Value | Meaning | Action for orchestrator |
|-------|---------|------------------------|
| `good` | Fresh value from a reliable source | Safe to act on |
| `stale` | Beyond cache TTL, no fresher data available | Act with caution, consider re-read |
| `degraded` | Source operational but outside normal parameters | SHOULD NOT act; flag for human review |
| `error` | Read failed; value absent or unreliable | MUST NOT act on this value |

When `quality` is `error`, the `value` field MAY be `null` or absent.

### 6.2 `do_*` response

REQUIRED fields:

```json
{
  "status": "success | partial | failed",
  "idempotency_key": "string",
  "compensable": true,
  "timestamp": "ISO 8601"
}
```

REQUIRED when `compensable` is `true`:

```json
{
  "compensation_hint": "string"
}
```

REQUIRED when the operation sets a measurable value:

```json
{
  "applied_value": "<any>",
  "previous_value": "<any>"
}
```

RECOMMENDED fields:

```json
{
  "side_effects": ["string"]
}
```

**`status` semantics:**

| Value | Meaning |
|-------|---------|
| `success` | Operation completed fully; side effects applied |
| `partial` | Operation partially applied; `side_effects` list reflects what was applied |
| `failed` | Operation did not apply; no side effects committed |

**`compensation_hint` format:**

The hint MUST be a human- and machine-readable string describing the reversal operation. RECOMMENDED format: `"call {tool_name} with {parameter}: {value}"`.

Example: `"call do_set_fan_speed with value: 30"`

### 6.3 `can_do` response — CapabilityReport

REQUIRED fields:

```json
{
  "query_id": "uuid-v4",
  "feasible": true,
  "candidates": [],
  "blocked": []
}
```

RECOMMENDED fields:

```json
{
  "context": {},
  "metadata": {}
}
```

**Candidate object — REQUIRED fields:**

```json
{
  "capability": "string",
  "source": "string",
  "confidence": 0.92,
  "permission": "allowed",
  "valid_until": "ISO 8601"
}
```

**Candidate object — RECOMMENDED fields:**

```json
{
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
  "estimated_latency_ms": 50
}
```

**Blocked object — REQUIRED fields:**

```json
{
  "capability": "string",
  "source": "string",
  "permission": "policy_denied",
  "reason": "string"
}
```

**Blocked object — OPTIONAL fields:**

```json
{
  "details": "string"
}
```

**Context object — OPTIONAL:**

```json
{
  "related_reads": ["string"],
  "current_observations": {}
}
```

`related_reads` is a list of `read_*` tool names the orchestrator MAY call for additional context before executing a `do_*`.

**Metadata object — RECOMMENDED:**

```json
{
  "timestamp": "ISO 8601",
  "total_latency_ms": 120
}
```

---

## 7. JSON Schema Definitions

### 7.1 `read_*` response schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/alexlqi/proMCP/schemas/read-response.json",
  "title": "proMCP read_* response",
  "type": "object",
  "required": ["value", "timestamp", "quality"],
  "properties": {
    "value": {},
    "timestamp": {
      "type": "string",
      "format": "date-time"
    },
    "quality": {
      "type": "string",
      "enum": ["good", "stale", "degraded", "error"]
    },
    "unit": {
      "type": ["string", "null"]
    }
  }
}
```

### 7.2 `do_*` response schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/alexlqi/proMCP/schemas/do-response.json",
  "title": "proMCP do_* response",
  "type": "object",
  "required": ["status", "idempotency_key", "compensable", "timestamp"],
  "properties": {
    "status": {
      "type": "string",
      "enum": ["success", "partial", "failed"]
    },
    "idempotency_key": {
      "type": "string",
      "minLength": 1
    },
    "applied_value": {},
    "previous_value": {},
    "side_effects": {
      "type": "array",
      "items": { "type": "string" }
    },
    "compensable": {
      "type": "boolean"
    },
    "compensation_hint": {
      "type": ["string", "null"]
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    }
  },
  "if": {
    "properties": { "compensable": { "const": true } }
  },
  "then": {
    "required": ["compensation_hint"]
  }
}
```

### 7.3 `can_do` input schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/alexlqi/proMCP/schemas/can-do-input.json",
  "title": "proMCP can_do input",
  "type": "object",
  "required": ["intent"],
  "properties": {
    "intent": {
      "type": "object",
      "required": ["semantic_tags"],
      "properties": {
        "semantic_tags": {
          "type": "array",
          "items": { "type": "string" },
          "minItems": 1,
          "description": "Tags describing the desired capability category"
        },
        "action": {
          "type": "string",
          "enum": ["read", "create", "update", "delete", "toggle", "increase", "decrease", "set"],
          "description": "Intended action direction"
        },
        "target": {
          "type": "string",
          "description": "The property or resource being targeted"
        },
        "value": {
          "description": "Optional target value"
        },
        "location": {
          "type": "string",
          "description": "Logical scope (zone, region, resource group)"
        }
      }
    },
    "scope": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Optional list of capability names or source IDs to constrain search"
    }
  }
}
```

### 7.4 `can_do` CapabilityReport schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/alexlqi/proMCP/schemas/capability-report.json",
  "title": "proMCP CapabilityReport",
  "type": "object",
  "required": ["query_id", "feasible", "candidates", "blocked"],
  "properties": {
    "query_id": {
      "type": "string",
      "format": "uuid"
    },
    "feasible": {
      "type": "boolean"
    },
    "candidates": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["capability", "source", "confidence", "permission", "valid_until"],
        "properties": {
          "capability": { "type": "string" },
          "source": { "type": "string" },
          "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0
          },
          "permission": {
            "type": "string",
            "enum": [
              "allowed",
              "requires_human_approval",
              "policy_denied",
              "rate_limited",
              "cooldown_active",
              "out_of_range",
              "permission_insufficient",
              "source_unreachable",
              "partition_no_quorum"
            ]
          },
          "valid_until": {
            "type": "string",
            "format": "date-time"
          },
          "current_state": {
            "type": "object",
            "properties": {
              "value": {},
              "unit": { "type": ["string", "null"] },
              "timestamp": { "type": "string", "format": "date-time" }
            }
          },
          "constraints": {
            "type": "object",
            "properties": {
              "min": { "type": ["number", "null"] },
              "max": { "type": ["number", "null"] },
              "unit": { "type": ["string", "null"] },
              "enum_values": {
                "type": "array",
                "items": { "type": "string" }
              }
            }
          },
          "side_effects": {
            "type": "array",
            "items": { "type": "string" }
          },
          "estimated_latency_ms": { "type": "integer" }
        }
      }
    },
    "blocked": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["capability", "source", "permission", "reason"],
        "properties": {
          "capability": { "type": "string" },
          "source": { "type": "string" },
          "permission": { "type": "string" },
          "reason": { "type": "string" },
          "details": { "type": ["string", "null"] }
        }
      }
    },
    "context": {
      "type": "object",
      "properties": {
        "related_reads": {
          "type": "array",
          "items": { "type": "string" }
        },
        "current_observations": {
          "type": "object"
        }
      }
    },
    "metadata": {
      "type": "object",
      "properties": {
        "timestamp": { "type": "string", "format": "date-time" },
        "total_latency_ms": { "type": "integer" }
      }
    }
  }
}
```

---

## 8. The Canonical Orchestration Pattern

proMCP defines a four-step execution contract. Implementations SHOULD follow this pattern for any mutation with non-trivial side effects.

```
Step 1 — PLAN
  can_do(intent_query)
  → Returns CapabilityReport with candidates[], blocked[], context
  → Orchestrator selects candidate with permission: allowed and highest confidence
  → Orchestrator records valid_until for selected candidate

Step 2 — OBSERVE  [parallelizable]
  read_*(required_state_A)
  read_*(required_state_B)
  read_*(required_state_N)
  → All read_* MAY execute concurrently
  → Orchestrator checks quality on every response
  → If any quality is "error": abort
  → If any quality is "degraded": escalate to human review before proceeding

Step 3 — EXECUTE
  Assert: now() < valid_until for selected candidate
  If assertion fails: return to Step 1
  do_*(action, idempotency_key=uuid(), payload)
  → Orchestrator retains idempotency_key
  → On network failure: retry with same idempotency_key (idempotent by contract)
  → On status: "failed": check compensable, initiate compensation if prior steps succeeded
  → On status: "partial": log side_effects applied, initiate selective compensation

Step 4 — VERIFY
  read_*(post_condition_state)
  → Compare observed value against expected post-state
  → If quality is "degraded" or "error": flag for human review
  → If post-state diverges from expected: log anomaly, do not silently succeed
```

### 8.1 When to skip steps

| Step | May be skipped when |
|------|-------------------|
| Step 1 (`can_do`) | The tool and its current permission are known with certainty AND `do_*` is `compensable: true` |
| Step 2 (`read_*`) | No prior state is required for the mutation logic |
| Step 3 (`do_*`) | Plan-only mode — orchestrator is building an execution plan without committing |
| Step 4 (`read_*`) | Side effects are entirely internal and not observable via any `read_*` tool |

Skipping Step 1 for a `compensable: false` mutation is an anti-pattern (§15).

---

## 9. Idempotency Contract

Every `do_*` tool MUST implement idempotency keyed on `idempotency_key`.

### 9.1 Client responsibilities

The client (orchestrator) MUST:
- Generate a unique `idempotency_key` per logical operation (not per retry)
- Pass the same `idempotency_key` on every retry of the same operation
- Retain `idempotency_key` for the duration of any compensation or audit trail

The client SHOULD use UUIDv4 for `idempotency_key` generation.

### 9.2 Server responsibilities

The server MUST:
- Accept `idempotency_key` as an input parameter on every `do_*` tool
- Return the same `status` and `applied_value` for duplicate calls with the same key within a deduplication window
- Not re-apply side effects on duplicate calls

The deduplication window SHOULD be at least 24 hours. The server MAY declare its deduplication window in the tool description.

### 9.3 Key format

`idempotency_key` MUST be a non-empty string. RECOMMENDED: UUIDv4 (`xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx`).

---

## 10. Compensation Contract

### 10.1 Declaration

Every `do_*` response MUST declare `compensable` as a boolean.

When `compensable: true`, the response MUST include `compensation_hint` — a string describing the tool call needed to reverse the effect.

### 10.2 Compensation hint format

The hint MUST be human-readable. The RECOMMENDED machine-parseable format is:

```
"{tool_name} {parameter_name}={value}"
```

Examples:
- `"do_set_fan_speed value=30"`
- `"do_update_inventory sku=001 delta=-50"`
- `"do_close_valve_main"`

### 10.3 Orchestrator behavior on failure

When a `do_*` returns `status: failed` and the orchestrator has already executed prior steps with side effects in the same workflow:

1. Identify all prior `do_*` calls in the workflow with `compensable: true`
2. Execute compensations in reverse order
3. Log each compensation with the original `idempotency_key` and a new compensation `idempotency_key`
4. Declare workflow status as `compensated` or `partial_compensation` depending on outcome

When `compensable: false` and `status: failed`, the orchestrator MUST escalate to human review. It MUST NOT silently proceed.

---

## 11. Staleness and Validity Contract

### 11.1 `quality` on `read_*`

Every `read_*` response MUST include a `quality` field. The orchestrator MUST NOT act on a value with `quality: error`. The orchestrator SHOULD NOT act on a value with `quality: degraded` without human review.

### 11.2 `valid_until` on `can_do` candidates

Every candidate in a CapabilityReport MUST include `valid_until` as an ISO 8601 datetime.

The orchestrator MUST check `valid_until` before executing a `do_*` derived from a prior `can_do` call. If `now() >= valid_until`, the orchestrator MUST re-call `can_do` before proceeding.

### 11.3 Setting `valid_until`

The server SHOULD set `valid_until` based on the volatility of the underlying permission and state:

| Permission volatility | Recommended `valid_until` window |
|----------------------|----------------------------------|
| Static (API key auth, fixed policy) | 60–300 seconds |
| Dynamic (rate limits, cooldowns) | 5–30 seconds |
| Physical state (sensor-dependent) | 1–5 seconds |
| Safety-critical actuators | 0–1 seconds (require fresh `can_do` per execution) |

A server that cannot determine volatility SHOULD set `valid_until` to 5 seconds from response time.

---

## 12. Permission Model

### 12.1 Permission enum

The `permission` field MUST use one of the following values:

| Value | Applies to | Meaning |
|-------|-----------|---------|
| `allowed` | candidates | Action will execute; all checks pass |
| `requires_human_approval` | candidates, blocked | Execution requires explicit human confirmation |
| `policy_denied` | blocked | Local policy unconditionally rejects the action |
| `rate_limited` | blocked | Rate limit for this tool is exhausted for the current window |
| `cooldown_active` | blocked | Mandatory cooldown period from a prior execution is active |
| `out_of_range` | blocked | Requested value is outside the declared bounds for this tool |
| `permission_insufficient` | blocked | Caller's identity or role does not meet the tool's requirement |
| `source_unreachable` | blocked | The tool's backing resource is offline or unreachable |
| `partition_no_quorum` | blocked | A distributed quorum requirement is not met |

### 12.2 `feasible` field

`feasible` MUST be `true` if and only if at least one candidate has `permission: allowed`.

`feasible: false` with a non-empty `candidates` array means candidates exist but none are currently executable. The orchestrator SHOULD inspect `blocked` to determine whether the situation is recoverable.

### 12.3 Handling `requires_human_approval`

When a candidate has `permission: requires_human_approval`, the orchestrator MUST NOT proceed to `do_*` autonomously. It MUST surface the approval requirement to a human operator and await explicit confirmation before continuing.

---

## 13. Tool Density Guidelines

### 13.1 Recommended limits

| Metric | Recommended | Hard limit |
|--------|-------------|------------|
| Tools per server | ≤ 8 | No protocol limit |
| `do_*` tools per server | ≤ 5 | No protocol limit |
| `read_*` tools per server | ≤ 6 | No protocol limit |

Tool selection accuracy in language models degrades measurably above 8 tools per server. Servers that need to expose more tools SHOULD split by domain or by workflow phase.

### 13.2 Grouping strategy

When a domain requires more than 8 tools, split into phase-specific servers:

```
inventory-read-server   → read_stock, read_sku, read_location, read_turnover
inventory-write-server  → do_update_stock, do_create_sku, do_transfer, can_do
```

The orchestrator exposes only the relevant server to the agent per phase of the workflow.

---

## 14. Domain Extension Contract

### 14.1 Extension rules

A domain extension of proMCP MUST:

1. Be a strict superset of proMCP response schemas — all REQUIRED proMCP fields MUST be present with identical semantics
2. Not redefine any field defined by proMCP with different semantics or types
3. Declare its proMCP base version in its own spec header: `promcp_base: "0.3.0"`
4. Document every field it adds beyond the proMCP base

A domain extension MAY:

- Add fields to any response schema
- Specialize `can_do` with domain-specific routing mechanisms
- Define manifest formats binding capabilities to domain resources
- Define additional permission enum values (MUST use a namespaced prefix, e.g. `domain_*`)

### 14.2 Reference extension

**[PhysMCP](https://physmcp.org)** (Physical Model Context Protocol) is the canonical reference extension of proMCP for physical-world IoT deployments.

PhysMCP extends proMCP with:
- Hardware interface bindings (I2C, GPIO, Modbus, RS-485, BACnet, OPC-UA)
- Peer-to-peer semantic mesh with gossip-based capability discovery
- Floating coordinator protocol for distributed `can_do` queries
- Device profiles: Full, Lite, Proxy, Aggregator
- `physmcp.manifest.yml` — declarative capability-to-hardware binding
- `physmcp.policy.yml` — local policy enforcement with time windows, quorum, range guards
- Network partition detection and recovery
- Additional `read_*` fields: `unit` (REQUIRED for physical quantities)
- Additional `do_*` fields: `applied_value` and `previous_value` (REQUIRED when setting measurable values)

The `quality`, `valid_until`, `permission` enum, and `CapabilityReport` structure in proMCP v0.2 were derived from the PhysMCP specification.

---

## 15. Anti-Patterns

### AP-1: Side-effect tool named `read_*`

Using `read_` prefix on a tool that mutates state. This destroys the orchestrator's ability to safely parallelize reads and breaks the planning model.

**Detection:** Any tool whose description includes words like "create", "update", "delete", "set", "reset", "trigger", "send" SHOULD be renamed to `do_*`.

### AP-2: Missing `idempotency_key`

A `do_*` tool that does not accept or generate `idempotency_key`. Makes retries unsafe. A network timeout becomes a potential double-execution with no recovery path.

### AP-3: Skipping `can_do` before `compensable: false` mutations

Executing a `do_*` with `compensable: false` without a prior `can_do` check. If the mutation fails after partial side effects in a multi-step workflow, there is no rollback path and no recovery signal.

### AP-4: Acting on expired `valid_until`

Executing a `do_*` against a candidate whose `valid_until` has passed. Permissions change. Rate limits reset. Cooldowns expire. Cached preconditions are invalid.

### AP-5: Acting on `quality: error` or `quality: degraded`

Proceeding with a mutation based on a `read_*` that returned `error` or `degraded` quality. The orchestrator cannot know whether the observation reflects actual state.

### AP-6: `confidence < 0.7` treated as confirmed

Proceeding with a `do_*` against a candidate with `confidence` below 0.7 without human review. Low confidence indicates the semantic match between intent and capability is uncertain.

### AP-7: Generic tool names

Naming tools `do_action`, `read_data`, `do_update`. Generic names provide no semantic signal for tool selection and degrade model accuracy.

### AP-8: Conflating `blocked` with failure

Treating a `feasible: false` response as a permanent error. Blocked candidates may be recoverable — rate limits reset, cooldowns expire, permissions can be elevated. The orchestrator SHOULD inspect `permission` values to determine recoverability.

---

## 16. Compliance Checklist

### Server compliance

- [ ] Every tool name starts with `read_`, `do_`, or is exactly `can_do`
- [ ] Every tool name is `lowercase_snake_case`
- [ ] Every `read_*` response includes `value`, `timestamp`, `quality`
- [ ] `quality` value is one of: `good`, `stale`, `degraded`, `error`
- [ ] Every `do_*` response includes `status`, `idempotency_key`, `compensable`, `timestamp`
- [ ] Every `do_*` accepts `idempotency_key` as input
- [ ] Every `do_*` with `compensable: true` includes `compensation_hint`
- [ ] `can_do` tool is present and is the only generic tool
- [ ] Every `can_do` candidate includes `capability`, `source`, `confidence`, `permission`, `valid_until`
- [ ] Every `can_do` blocked entry includes `capability`, `source`, `permission`, `reason`
- [ ] `feasible` is `true` iff at least one candidate has `permission: allowed`
- [ ] `permission` values use only the defined enum

### Orchestrator compliance

- [ ] All `read_*` calls in a workflow step are fanned out in parallel
- [ ] `quality: error` aborts the workflow step
- [ ] `quality: degraded` escalates to human review
- [ ] `valid_until` is checked before every `do_*` execution
- [ ] `idempotency_key` is retained per operation and reused on retry
- [ ] `compensable: false` failures escalate to human review
- [ ] `confidence < 0.7` escalates to human review
- [ ] `requires_human_approval` never proceeds autonomously

---

## 17. Examples

### 17.1 Software domain — inventory management

**Scenario:** An agent needs to transfer 50 units of SKU-001 from warehouse A to warehouse B.

**Step 1 — PLAN**

Request:
```json
{
  "intent": {
    "semantic_tags": ["inventory", "transfer", "warehouse"],
    "action": "update",
    "target": "stock_location",
    "value": 50
  }
}
```

Response (CapabilityReport):
```json
{
  "query_id": "a1b2c3d4-e5f6-4789-abcd-ef0123456789",
  "feasible": true,
  "candidates": [
    {
      "capability": "do_transfer_stock",
      "source": "inventory-server",
      "confidence": 0.95,
      "permission": "allowed",
      "valid_until": "2026-04-30T16:05:00Z",
      "current_state": { "value": null, "unit": null, "timestamp": "2026-04-30T16:04:00Z" },
      "constraints": { "min": 1, "max": 10000, "unit": "units" },
      "side_effects": ["stock_level_change_source", "stock_level_change_destination", "audit_log_entry"],
      "estimated_latency_ms": 80
    }
  ],
  "blocked": [],
  "context": {
    "related_reads": ["read_stock_warehouse_a", "read_stock_warehouse_b"],
    "current_observations": {}
  },
  "metadata": { "timestamp": "2026-04-30T16:04:00Z", "total_latency_ms": 45 }
}
```

**Step 2 — OBSERVE (parallel)**

`read_stock_warehouse_a` response:
```json
{
  "value": 200,
  "unit": "units",
  "timestamp": "2026-04-30T16:04:01Z",
  "quality": "good"
}
```

`read_stock_warehouse_b` response:
```json
{
  "value": 30,
  "unit": "units",
  "timestamp": "2026-04-30T16:04:01Z",
  "quality": "good"
}
```

**Step 3 — EXECUTE**

Request:
```json
{
  "idempotency_key": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "sku": "SKU-001",
  "quantity": 50,
  "source_warehouse": "A",
  "destination_warehouse": "B"
}
```

Response:
```json
{
  "status": "success",
  "idempotency_key": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "applied_value": 50,
  "previous_value": 0,
  "side_effects": ["stock_level_change_source", "stock_level_change_destination", "audit_log_entry"],
  "compensable": true,
  "compensation_hint": "do_transfer_stock sku=SKU-001 quantity=50 source_warehouse=B destination_warehouse=A",
  "timestamp": "2026-04-30T16:04:02Z"
}
```

**Step 4 — VERIFY (parallel)**

`read_stock_warehouse_a` → `value: 150, quality: good` ✓
`read_stock_warehouse_b` → `value: 80, quality: good` ✓

---

### 17.2 Blocked scenario — rate limit

**Step 1 — PLAN**

`can_do` returns:
```json
{
  "query_id": "b2c3d4e5-f6a7-4890-bcde-f01234567890",
  "feasible": false,
  "candidates": [],
  "blocked": [
    {
      "capability": "do_transfer_stock",
      "source": "inventory-server",
      "permission": "rate_limited",
      "reason": "Transfer limit of 10/hour exceeded",
      "details": "Window resets at 2026-04-30T17:00:00Z"
    }
  ],
  "context": { "related_reads": [], "current_observations": {} },
  "metadata": { "timestamp": "2026-04-30T16:45:00Z", "total_latency_ms": 12 }
}
```

Orchestrator behavior: `feasible: false`, `permission: rate_limited` → recoverable. Schedule retry after `2026-04-30T17:00:00Z`. Do not escalate to human review.

---

### 17.3 Human approval required

`can_do` returns candidate with:
```json
{
  "capability": "do_bulk_delete_records",
  "permission": "requires_human_approval",
  "confidence": 0.98,
  "valid_until": "2026-04-30T16:10:00Z"
}
```

Orchestrator behavior: surface to human operator with full candidate details and `valid_until`. Await explicit confirmation. Do NOT proceed autonomously.

---

## 18. Changelog

### v0.3.0 (2026-07-22)
- No spec-content changes; released alongside the FastMCP transport adapter (ADR-001) and transport naming fixes. See `CHANGELOG.md` for tooling details.

### v0.2.0 (2026-04-30)
- Replaced `freshness` enum on `read_*` with `quality: good|stale|degraded|error` (derived from PhysMCP)
- Added `applied_value` and `previous_value` to `do_*` response (derived from PhysMCP)
- Replaced flat `can_do` response with full CapabilityReport structure: `candidates[]`, `blocked[]`, `context`, `metadata` (derived from PhysMCP)
- Replaced `expires_at` on response root with `valid_until` per candidate
- Added `confidence` float per candidate with 0.7 threshold guidance
- Added typed `permission` enum with 9 values including `partition_no_quorum`
- Added `side_effects` to candidate objects (pre-execution visibility)
- Added domain extension contract (§14) with superset rule
- Added formal JSON Schema definitions (§7)
- Added idempotency contract (§9)
- Added compensation contract (§10)
- Added staleness and validity contract (§11)
- Added tool density guidelines (§13)
- Expanded examples (§17)

### v0.1.0 (2026-04-30)
- Initial declaration: `read_*`, `do_*`, `can_do` triad
- Basic response shapes
- Canonical four-step orchestration pattern
- Initial anti-patterns

---

*proMCP is not affiliated with Anthropic. It is a community convention built on top of the Model Context Protocol.*

*Author: [@alexlqi](https://github.com/alexlqi)*
*Organizations: EnthalpyDW / GoMethos*
*License: CC-BY-SA 4.0*
*Repository: [github.com/alexlqi/proMCP](https://github.com/alexlqi/proMCP)*
