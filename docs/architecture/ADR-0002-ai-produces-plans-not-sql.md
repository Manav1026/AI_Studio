# ADR-0002 — The AI produces a structured plan; code produces and validates SOQL

Status: Accepted · Date: 2026-10-01

## Decision
The model returns a JSON `QueryPlan` (object, fields, filters, grouping, aggregates, sort, limit) constrained by a
JSON schema and grounded in a catalog subset. `plan_to_soql()` compiles it deterministically, typing and escaping
values from catalog field types. Every query — AI-built, user-edited, saved-template or MCP — passes the same
validator and policy before execution, and is re-validated at execution time.

## Consequences
- Prompt injection cannot produce DML or unknown fields; worst case is a validation rejection.
- AI vendors are swappable behind `AIGateway` (mock / OpenAI / Anthropic); prompts are versioned (`nl2plan-v1`).
- Saved templates skip the model entirely, lowering cost and latency for repeated questions.
