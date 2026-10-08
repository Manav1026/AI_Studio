"""Versioned prompts. Bump PROMPT_VERSION whenever wording changes so evals and usage can be compared."""
import json

PROMPT_VERSION = "nl2plan-v1"

PLAN_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent", "root_object", "objects", "fields", "filters", "aggregations", "group_by",
                 "order_by", "limit", "read_only", "explanation"],
    "properties": {
        "intent": {"type": "string"},
        "root_object": {"type": "string"},
        "objects": {"type": "array", "items": {"type": "string"}},
        "fields": {"type": "array", "items": {"type": "string"}},
        "filters": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["field", "operator", "value"],
            "properties": {"field": {"type": "string"}, "operator": {"type": "string"},
                           "value": {"type": ["string", "number", "boolean", "null", "array"],
                                     "items": {"type": ["string", "number"]}}}}},
        "aggregations": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["function", "field", "alias"],
            "properties": {"function": {"type": "string", "enum": ["COUNT", "COUNT_DISTINCT", "SUM", "AVG",
                                                                   "MIN", "MAX"]},
                           "field": {"type": ["string", "null"]}, "alias": {"type": ["string", "null"]}}}},
        "group_by": {"type": "array", "items": {"type": "string"}},
        "order_by": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["field", "direction"],
            "properties": {"field": {"type": "string"}, "direction": {"type": "string", "enum": ["ASC", "DESC"]}}}},
        "limit": {"type": ["integer", "null"]},
        "read_only": {"type": "boolean", "enum": [True]},
        "explanation": {"type": "string"},
    },
}

SYSTEM_PROMPT = """You translate business questions into a STRUCTURED QUERY PLAN for Salesforce (SOQL subset).
Rules:
- Use ONLY objects and fields present in the provided catalog context. Never invent names.
- root_object is the FROM object. Field paths are relative to root_object; use parent relationship
  names for lookups (e.g. from Opportunity use "Account.Name").
- Child-relationship subqueries, HAVING, TYPEOF, and any write operation are NOT allowed.
- Filters: operator one of = != < > <= >= LIKE IN "NOT IN". Date fields may use SOQL date literals
  as the value (THIS_YEAR, LAST_MONTH, LAST_N_DAYS:30 ...). Booleans are true/false.
- If you aggregate, every non-aggregated field must be in group_by. order_by may reference an
  aggregation alias.
- Always set a sensible limit (<= 200) unless the result is a single aggregate.
- read_only must be true. explanation: one or two plain-English sentences for a business user.
Return ONLY the JSON object matching the schema."""


def render_user_prompt(question: str, context: dict) -> str:
    return ("Catalog context (only these objects/fields exist):\n"
            + json.dumps(context["objects"], separators=(",", ":"))
            + f"\n\nToday's date: {context.get('today')}\nQuestion: {question}")
