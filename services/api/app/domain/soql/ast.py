from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union


@dataclass(frozen=True)
class FieldRef:
    path: tuple[str, ...]

    @property
    def dotted(self) -> str:
        return ".".join(self.path)


@dataclass(frozen=True)
class AggregateExpr:
    func: str  # COUNT|COUNT_DISTINCT|SUM|AVG|MIN|MAX
    field: FieldRef | None  # None => COUNT()

    @property
    def text(self) -> str:
        return f"{self.func}({self.field.dotted if self.field else ''})"


Expr = Union[FieldRef, AggregateExpr]


@dataclass(frozen=True)
class Literal:
    kind: str  # string|number|boolean|null|date|datetime|date_literal
    value: Any
    n: int | None = None  # for LAST_N_DAYS:n style literals

    def to_soql(self) -> str:
        if self.kind == "string":
            return "'" + str(self.value).replace("\\", "\\\\").replace("'", "\\'") + "'"
        if self.kind == "boolean":
            return "true" if self.value else "false"
        if self.kind == "null":
            return "null"
        if self.kind == "date_literal":
            return f"{self.value}:{self.n}" if self.n is not None else str(self.value)
        return str(self.value)


@dataclass(frozen=True)
class Comparison:
    field: FieldRef
    op: str  # = != < > <= >= LIKE IN NOT IN
    value: Literal | tuple[Literal, ...]


@dataclass(frozen=True)
class BoolOp:
    op: str  # AND|OR
    items: tuple[Condition, ...]


@dataclass(frozen=True)
class NotOp:
    item: Condition


Condition = Union[Comparison, BoolOp, NotOp]


@dataclass(frozen=True)
class SelectItem:
    expr: Expr
    alias: str | None = None


@dataclass(frozen=True)
class OrderItem:
    expr: Expr
    direction: str = "ASC"
    nulls: str | None = None


@dataclass
class SoqlQuery:
    select: list[SelectItem]
    from_object: str
    where: Condition | None = None
    group_by: list[FieldRef] = field(default_factory=list)
    order_by: list[OrderItem] = field(default_factory=list)
    limit: int | None = None
    offset: int | None = None

    @property
    def has_aggregates(self) -> bool:
        return any(isinstance(s.expr, AggregateExpr) for s in self.select)


def iter_comparisons(cond: Condition | None):
    if cond is None:
        return
    if isinstance(cond, Comparison):
        yield cond
    elif isinstance(cond, BoolOp):
        for c in cond.items:
            yield from iter_comparisons(c)
    elif isinstance(cond, NotOp):
        yield from iter_comparisons(cond.item)


def expr_to_soql(e: Expr) -> str:
    return e.dotted if isinstance(e, FieldRef) else e.text


def cond_to_soql(c: Condition, top: bool = True) -> str:
    if isinstance(c, Comparison):
        if isinstance(c.value, tuple):
            vals = ", ".join(v.to_soql() for v in c.value)
            return f"{c.field.dotted} {c.op} ({vals})"
        return f"{c.field.dotted} {c.op} {c.value.to_soql()}"
    if isinstance(c, NotOp):
        return f"NOT ({cond_to_soql(c.item)})"
    inner = f" {c.op} ".join(cond_to_soql(i, top=False) for i in c.items)
    return inner if top else f"({inner})"


def to_soql(q: SoqlQuery) -> str:
    parts = ["SELECT " + ", ".join(expr_to_soql(s.expr) + (f" {s.alias}" if s.alias else "") for s in q.select),
             f"FROM {q.from_object}"]
    if q.where is not None:
        parts.append("WHERE " + cond_to_soql(q.where))
    if q.group_by:
        parts.append("GROUP BY " + ", ".join(f.dotted for f in q.group_by))
    if q.order_by:
        parts.append("ORDER BY " + ", ".join(
            expr_to_soql(o.expr) + f" {o.direction}" + (f" NULLS {o.nulls}" if o.nulls else "") for o in q.order_by))
    if q.limit is not None:
        parts.append(f"LIMIT {q.limit}")
    if q.offset is not None:
        parts.append(f"OFFSET {q.offset}")
    return " ".join(parts)
