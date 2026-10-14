"""Structured query plan: the contract between the AI step and the deterministic SOQL builder."""
from __future__ import annotations

import re
from datetime import date
from typing import Any
from typing import Literal as TLiteral

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.catalog_view import DATE_TYPES, DATETIME_TYPES, NUMERIC_TYPES, CatalogView
from app.domain.soql.ast import (
    AggregateExpr,
    BoolOp,
    Comparison,
    FieldRef,
    Literal,
    OrderItem,
    SelectItem,
    SoqlQuery,
    to_soql,
)
from app.domain.soql.parser import DATE_LITERALS, DATE_N_LITERALS

Operator = TLiteral["=", "!=", "<", ">", "<=", ">=", "LIKE", "IN", "NOT IN"]
AggFunc = TLiteral["COUNT", "COUNT_DISTINCT", "SUM", "AVG", "MIN", "MAX"]


class PlanFilter(BaseModel):
    field: str
    operator: str = "="
    value: Any = None

    @model_validator(mode="after")
    def _date_literal_operator(self):
        # Accept the shorthand {"field": "CloseDate", "operator": "THIS_YEAR"}
        if self.operator.upper() in DATE_LITERALS or self.operator.upper().split(":")[0] in DATE_N_LITERALS:
            self.value, self.operator = self.operator.upper(), "="
        self.operator = self.operator.upper()
        if self.operator not in {"=", "!=", "<", ">", "<=", ">=", "LIKE", "IN", "NOT IN"}:
            raise ValueError(f"Unsupported operator {self.operator}")
        return self


class PlanAggregation(BaseModel):
    function: AggFunc
    field: str | None = None
    alias: str | None = None

    @field_validator("function", mode="before")
    @classmethod
    def _upper(cls, v):
        return str(v).upper()


class PlanOrder(BaseModel):
    field: str
    direction: TLiteral["ASC", "DESC"] = "ASC"

    @field_validator("direction", mode="before")
    @classmethod
    def _upper(cls, v):
        return str(v).upper()


class QueryPlan(BaseModel):
    intent: str
    root_object: str
    objects: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    filters: list[PlanFilter] = Field(default_factory=list)
    aggregations: list[PlanAggregation] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    order_by: list[PlanOrder] = Field(default_factory=list)
    limit: int | None = Field(default=None, ge=1, le=2000)
    read_only: TLiteral[True] = True
    explanation: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _single_aggregation(cls, data):
        if isinstance(data, dict) and data.get("aggregation") and not data.get("aggregations"):
            data = {**data, "aggregations": [data["aggregation"]]}
        return data


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DT = re.compile(r"^\d{4}-\d{2}-\d{2}T")


class PlanBuildError(ValueError):
    pass


def _strip_root(root: str, path: str) -> tuple[str, ...]:
    parts = tuple(p for p in path.strip().split(".") if p)
    if len(parts) > 1 and parts[0].lower() == root.lower():
        parts = parts[1:]
    return parts


def _literal_for(ftype: str | None, value: Any) -> Literal:
    if value is None:
        return Literal("null", None)
    if isinstance(value, bool):
        return Literal("boolean", value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Literal("number", value)
    sval = str(value).strip()
    up = sval.upper()
    if ftype in DATE_TYPES | DATETIME_TYPES:
        if up in DATE_LITERALS:
            return Literal("date_literal", up)
        if ":" in up and up.split(":")[0] in DATE_N_LITERALS and up.split(":")[1].isdigit():
            return Literal("date_literal", up.split(":")[0], int(up.split(":")[1]))
        if ftype in DATE_TYPES and _ISO_DATE.match(sval):
            date.fromisoformat(sval)
            return Literal("date", sval)
        if ftype in DATETIME_TYPES and _ISO_DATE.match(sval):
            return Literal("datetime", f"{sval}T00:00:00Z")
        if ftype in DATETIME_TYPES and _ISO_DT.match(sval):
            return Literal("datetime", sval)
    if ftype in NUMERIC_TYPES:
        try:
            num = float(sval)
            return Literal("number", int(num) if num.is_integer() else num)
        except ValueError:
            pass
    if ftype == "boolean" and up in ("TRUE", "FALSE"):
        return Literal("boolean", up == "TRUE")
    return Literal("string", sval)


def plan_to_soql(plan: QueryPlan, catalog: CatalogView, default_limit: int = 50) -> str:
    """Deterministically compile a plan into SOQL. Type information comes from the catalog,
    so values are always quoted/escaped correctly (no string concatenation of model output)."""
    root_obj = catalog.obj(plan.root_object)
    if root_obj is None:
        raise PlanBuildError(f"Unknown root object {plan.root_object}")
    root = root_obj.name

    def ftype(path: tuple[str, ...]) -> str | None:
        f, _, _ = catalog.resolve_path(root, path)
        return f.type if f else None

    select: list[SelectItem] = []
    for f in plan.fields:
        ref = FieldRef(_strip_root(root, f))
        if ref.path and ref not in [s.expr for s in select]:
            select.append(SelectItem(ref))
    group_by = [FieldRef(_strip_root(root, g)) for g in plan.group_by]
    for g in group_by:
        if g not in [s.expr for s in select]:
            select.append(SelectItem(g))
    agg_exprs: dict[str, AggregateExpr] = {}
    for i, a in enumerate(plan.aggregations):
        field = None if a.field in (None, "", "*") else FieldRef(_strip_root(root, a.field))
        if field is None and a.function != "COUNT":
            raise PlanBuildError(f"{a.function} requires a field")
        expr = AggregateExpr(a.function, field)
        alias = re.sub(r"[^A-Za-z0-9_]", "", a.alias or "") or f"{a.function.lower()}_{i}"
        if alias[0].isdigit():
            alias = "a_" + alias
        agg_exprs[alias.lower()] = expr
        agg_exprs[expr.text.lower()] = expr
        select.append(SelectItem(expr, alias))
    if not select:
        select = [SelectItem(FieldRef(("Id",)))]

    conds = []
    for flt in plan.filters:
        path = _strip_root(root, flt.field)
        t = ftype(path)
        if flt.operator in ("IN", "NOT IN"):
            vals = flt.value if isinstance(flt.value, list) else [flt.value]
            conds.append(Comparison(FieldRef(path), flt.operator, tuple(_literal_for(t, v) for v in vals)))
        else:
            conds.append(Comparison(FieldRef(path), flt.operator, _literal_for(t, flt.value)))
    where = None if not conds else (conds[0] if len(conds) == 1 else BoolOp("AND", tuple(conds)))

    order_by = []
    for o in plan.order_by:
        key = o.field.strip()
        expr = agg_exprs.get(key.lower()) or agg_exprs.get(key.replace(" ", "").lower())
        if expr is None:
            m = re.match(r"^(COUNT_DISTINCT|COUNT|SUM|AVG|MIN|MAX)\((.*)\)$", key.replace(" ", ""), re.I)
            if m:
                inner = m.group(2)
                expr = AggregateExpr(m.group(1).upper(), FieldRef(_strip_root(root, inner)) if inner else None)
            else:
                expr = FieldRef(_strip_root(root, key))
        order_by.append(OrderItem(expr, o.direction, "LAST" if o.direction == "DESC" else None))

    is_scalar_agg = bool(plan.aggregations) and not group_by
    limit = plan.limit if plan.limit is not None else (None if is_scalar_agg else default_limit)
    q = SoqlQuery(select=select, from_object=root, where=where, group_by=group_by, order_by=order_by, limit=limit)
    return to_soql(q)
