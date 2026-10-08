"""Validation pipeline. AI output (and hand-written SOQL) is untrusted: the application, not the model,
decides whether a query is executable."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.catalog_view import DATE_TYPES, DATETIME_TYPES, NUMERIC_TYPES, TEXT_TYPES, CatalogView
from app.domain.policy import QueryPolicy
from app.domain.soql.ast import AggregateExpr, FieldRef, SoqlQuery, iter_comparisons, to_soql
from app.domain.soql.parser import SoqlParseError, parse_soql


@dataclass
class Issue:
    code: str
    message: str
    severity: str = "error"  # error|warning
    path: str | None = None

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "severity": self.severity, "path": self.path}


@dataclass
class ValidationResult:
    valid: bool
    issues: list[Issue] = field(default_factory=list)
    normalized_soql: str | None = None
    root_object: str | None = None
    referenced_objects: list[str] = field(default_factory=list)
    referenced_fields: list[str] = field(default_factory=list)
    is_aggregate: bool = False
    checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"valid": self.valid, "issues": [i.to_dict() for i in self.issues],
                "normalized_soql": self.normalized_soql, "root_object": self.root_object,
                "referenced_objects": self.referenced_objects, "referenced_fields": self.referenced_fields,
                "is_aggregate": self.is_aggregate, "checks": self.checks}


def _type_ok_for_literal(ftype: str, lit_kind: str, op: str) -> bool:
    if lit_kind == "null":
        return op in ("=", "!=")
    if op == "LIKE":
        return ftype in TEXT_TYPES and lit_kind == "string"
    if ftype in NUMERIC_TYPES:
        return lit_kind == "number"
    if ftype in DATE_TYPES:
        return lit_kind in ("date", "date_literal")
    if ftype in DATETIME_TYPES:
        return lit_kind in ("datetime", "date_literal")
    if ftype == "boolean":
        return lit_kind == "boolean" and op in ("=", "!=")
    if ftype in TEXT_TYPES:
        return lit_kind == "string" and (op in ("=", "!=", "IN", "NOT IN") or ftype not in ("picklist", "id"))
    return lit_kind == "string"


def validate_soql(soql: str, catalog: CatalogView, policy: QueryPolicy) -> ValidationResult:
    res = ValidationResult(valid=False)
    issues = res.issues

    # 1. Parser / static checks + read-only enforcement
    try:
        q: SoqlQuery = parse_soql(soql)
    except SoqlParseError as e:
        issues.append(Issue(e.code, str(e)))
        res.checks.append("parse")
        return res
    res.checks += ["parse", "read_only"]
    res.is_aggregate = q.has_aggregates

    # 2. Object existence / queryability / policy
    obj = catalog.obj(q.from_object)
    res.checks.append("object_exists")
    if obj is None:
        issues.append(Issue("unknown_object", f"Object {q.from_object} is not in the metadata catalog",
                            path=q.from_object))
        return res
    if not obj.queryable:
        issues.append(Issue("object_not_queryable", f"Object {obj.name} is not queryable", path=obj.name))
    res.checks.append("policy")
    if not policy.object_allowed(obj.name):
        issues.append(Issue("object_blocked_by_policy", f"Object {obj.name} is blocked by policy", path=obj.name))
    res.root_object = obj.name
    objects_seen = {obj.name}

    def check_field(ref: FieldRef, purpose: str):
        if len(ref.path) - 1 > policy.max_relationship_depth:
            issues.append(Issue("relationship_too_deep", f"{ref.dotted} exceeds max relationship depth "
                                f"{policy.max_relationship_depth}", path=ref.dotted))
            return None
        f, traversed, err = catalog.resolve_path(obj.name, ref.path)
        if err:
            code = "unknown_field" if len(ref.path) == 1 else "invalid_relationship_path"
            issues.append(Issue(code, err, path=ref.dotted))
            return None
        objects_seen.update(traversed)
        owner = traversed[-1]
        if not policy.field_allowed(owner, f.name):
            issues.append(Issue("field_blocked_by_policy", f"{owner}.{f.name} is blocked by policy", path=ref.dotted))
        if not f.queryable:
            issues.append(Issue("field_not_queryable", f"{owner}.{f.name} is not queryable", path=ref.dotted))
        if purpose == "filter" and not f.filterable:
            issues.append(Issue("field_not_filterable", f"{owner}.{f.name} cannot be filtered", path=ref.dotted))
        if purpose == "group" and not f.groupable:
            issues.append(Issue("field_not_groupable", f"{owner}.{f.name} cannot be grouped", path=ref.dotted))
        if purpose == "sort" and not f.sortable:
            issues.append(Issue("field_not_sortable", f"{owner}.{f.name} cannot be sorted", path=ref.dotted))
        if ref.dotted not in res.referenced_fields:
            res.referenced_fields.append(ref.dotted)
        return f

    # 3. Field existence, queryability, relationship paths
    res.checks += ["fields_exist", "relationship_paths"]
    if len(q.select) > policy.max_fields:
        issues.append(Issue("too_many_fields", f"At most {policy.max_fields} fields may be selected"))
    plain_selected: list[str] = []
    for item in q.select:
        if isinstance(item.expr, FieldRef):
            check_field(item.expr, "select")
            plain_selected.append(item.expr.dotted.lower())
        else:
            agg: AggregateExpr = item.expr
            if agg.field is not None:
                f = check_field(agg.field, "aggregate")
                if f is not None and agg.func in ("SUM", "AVG") and f.type not in NUMERIC_TYPES:
                    issues.append(Issue("aggregate_type_mismatch",
                                        f"{agg.func} requires a numeric field; {agg.field.dotted} is {f.type}",
                                        path=agg.text))
                if f is not None and agg.func in ("MIN", "MAX") and f.type in ("boolean", "textarea"):
                    issues.append(Issue("aggregate_type_mismatch", f"{agg.func} not valid for {f.type}",
                                        path=agg.text))

    # 4. Filters: operator/type compatibility, complexity
    res.checks += ["operator_types", "complexity"]
    comparisons = list(iter_comparisons(q.where))
    if len(comparisons) > policy.max_conditions:
        issues.append(Issue("too_many_conditions", f"At most {policy.max_conditions} conditions are allowed"))
    for c in comparisons:
        f = check_field(c.field, "filter")
        if f is None:
            continue
        values = c.value if isinstance(c.value, tuple) else (c.value,)
        for v in values:
            if not _type_ok_for_literal(f.type, v.kind, c.op):
                issues.append(Issue("operator_type_mismatch",
                                    f"{c.field.dotted} ({f.type}) {c.op} {v.to_soql()} is not a valid comparison",
                                    path=c.field.dotted))

    # 5. Aggregation / grouping rules
    group_keys = [g.dotted.lower() for g in q.group_by]
    for g in q.group_by:
        check_field(g, "group")
    if q.has_aggregates or q.group_by:
        for p in plain_selected:
            if p not in group_keys:
                issues.append(Issue("ungrouped_field",
                                    f"{p} must appear in GROUP BY when aggregates are used", path=p))

    # 6. ORDER BY
    for o in q.order_by:
        if isinstance(o.expr, FieldRef):
            check_field(o.expr, "sort")
            if (q.has_aggregates or q.group_by) and o.expr.dotted.lower() not in group_keys:
                issues.append(Issue("invalid_order_by", f"ORDER BY {o.expr.dotted} must be grouped or aggregated"))
        elif o.expr.field is not None:
            check_field(o.expr.field, "aggregate")

    # 7. Limit enforcement (inject default for record queries, cap for all)
    res.checks.append("limit")
    if q.limit is None:
        if not (q.has_aggregates and not q.group_by):
            q.limit = policy.default_limit
            issues.append(Issue("limit_injected", f"No LIMIT supplied; applied default LIMIT {policy.default_limit}",
                                severity="warning"))
    elif q.limit > policy.max_limit:
        issues.append(Issue("limit_capped", f"LIMIT {q.limit} reduced to maximum {policy.max_limit}",
                            severity="warning"))
        q.limit = policy.max_limit
    if q.offset is not None and q.offset > 2000:
        issues.append(Issue("offset_too_large", "OFFSET cannot exceed 2000"))

    res.referenced_objects = sorted(objects_seen)
    res.normalized_soql = to_soql(q)
    res.valid = not any(i.severity == "error" for i in issues)
    return res
