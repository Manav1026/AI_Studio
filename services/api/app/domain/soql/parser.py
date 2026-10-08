"""A strict parser for the read-only SOQL subset the prototype allows.

Anything outside the subset (DML-like clauses, FOR UPDATE, subqueries, TYPEOF, multiple statements)
is rejected *before* any Salesforce call. Extending the subset later is additive."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.soql.ast import (
    AggregateExpr,
    BoolOp,
    Comparison,
    Condition,
    FieldRef,
    Literal,
    NotOp,
    OrderItem,
    SelectItem,
    SoqlQuery,
)


class SoqlParseError(ValueError):
    def __init__(self, message: str, code: str = "soql_parse_error"):
        super().__init__(message)
        self.code = code


DATE_LITERALS = {
    "YESTERDAY", "TODAY", "TOMORROW", "LAST_WEEK", "THIS_WEEK", "NEXT_WEEK", "LAST_MONTH", "THIS_MONTH",
    "NEXT_MONTH", "LAST_90_DAYS", "NEXT_90_DAYS", "THIS_QUARTER", "LAST_QUARTER", "NEXT_QUARTER",
    "THIS_YEAR", "LAST_YEAR", "NEXT_YEAR", "THIS_FISCAL_QUARTER", "LAST_FISCAL_QUARTER", "THIS_FISCAL_YEAR",
    "LAST_FISCAL_YEAR",
}
DATE_N_LITERALS = {"LAST_N_DAYS", "NEXT_N_DAYS", "LAST_N_WEEKS", "NEXT_N_WEEKS", "LAST_N_MONTHS",
                   "NEXT_N_MONTHS", "LAST_N_QUARTERS", "NEXT_N_QUARTERS", "LAST_N_YEARS", "NEXT_N_YEARS"}
AGG_FUNCS = {"COUNT", "COUNT_DISTINCT", "SUM", "AVG", "MIN", "MAX"}
FORBIDDEN = {
    "UPDATE": "FOR UPDATE / DML is not allowed (read-only)",
    "INSERT": "DML is not allowed (read-only)", "DELETE": "DML is not allowed (read-only)",
    "UPSERT": "DML is not allowed (read-only)", "MERGE": "DML is not allowed (read-only)",
    "UNDELETE": "DML is not allowed (read-only)", "TYPEOF": "TYPEOF is not supported in the prototype",
    "HAVING": "HAVING is not supported in the prototype", "WITH": "WITH clauses are not supported",
    "USING": "USING SCOPE is not supported", "FOR": "FOR VIEW/REFERENCE/UPDATE is not allowed",
    "ALL": "ALL ROWS is not allowed",
}

_TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<string>'(?:\\.|[^'\\])*')
  | (?P<datetime>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))
  | (?P<date>\d{4}-\d{2}-\d{2})
  | (?P<number>-?\d+(?:\.\d+)?)
  | (?P<dateN>[A-Za-z_]+:\d+)
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)
  | (?P<op><=|>=|!=|<>|=|<|>)
  | (?P<punct>[(),])
  | (?P<bad>.)
""", re.VERBOSE)


@dataclass
class Tok:
    kind: str
    text: str

    @property
    def upper(self) -> str:
        return self.text.upper()


def tokenize(text: str) -> list[Tok]:
    toks: list[Tok] = []
    for m in _TOKEN_RE.finditer(text):
        kind = m.lastgroup
        if kind == "ws":
            continue
        if kind == "bad":
            ch = m.group()
            if ch == ";":
                raise SoqlParseError("Multiple statements / ';' are not allowed", "multiple_statements")
            raise SoqlParseError(f"Unexpected character {ch!r}")
        toks.append(Tok(kind, m.group()))
    return toks


class _Parser:
    def __init__(self, toks: list[Tok]):
        self.t = toks
        self.i = 0

    def peek(self, k: int = 0) -> Tok | None:
        j = self.i + k
        return self.t[j] if j < len(self.t) else None

    def next(self) -> Tok:
        tok = self.peek()
        if tok is None:
            raise SoqlParseError("Unexpected end of query")
        self.i += 1
        return tok

    def is_kw(self, *words: str, k: int = 0) -> bool:
        tok = self.peek(k)
        return tok is not None and tok.kind == "ident" and tok.upper in words

    def expect_kw(self, word: str) -> None:
        tok = self.next()
        if tok.kind != "ident" or tok.upper != word:
            raise SoqlParseError(f"Expected {word}, got {tok.text!r}")

    def expect_punct(self, p: str) -> None:
        tok = self.next()
        if tok.text != p:
            raise SoqlParseError(f"Expected {p!r}, got {tok.text!r}")

    def check_forbidden(self) -> None:
        tok = self.peek()
        if tok is not None and tok.kind == "ident" and tok.upper in FORBIDDEN:
            raise SoqlParseError(FORBIDDEN[tok.upper], "forbidden_clause")

    # --- grammar -----------------------------------------------------------------------------
    def parse(self) -> SoqlQuery:
        if not self.is_kw("SELECT"):
            raise SoqlParseError("Only SELECT queries are allowed (read-only)", "not_select")
        self.next()
        select = [self.select_item()]
        while self.peek() and self.peek().text == ",":
            self.next()
            select.append(self.select_item())
        self.expect_kw("FROM")
        obj = self.next()
        if obj.kind != "ident" or "." in obj.text:
            raise SoqlParseError("Invalid FROM object")
        q = SoqlQuery(select=select, from_object=obj.text)
        self.check_forbidden()
        if self.is_kw("WHERE"):
            self.next()
            q.where = self.condition()
        self.check_forbidden()
        if self.is_kw("GROUP"):
            self.next()
            self.expect_kw("BY")
            q.group_by = [self.field_ref()]
            while self.peek() and self.peek().text == ",":
                self.next()
                q.group_by.append(self.field_ref())
        self.check_forbidden()
        if self.is_kw("ORDER"):
            self.next()
            self.expect_kw("BY")
            q.order_by = [self.order_item()]
            while self.peek() and self.peek().text == ",":
                self.next()
                q.order_by.append(self.order_item())
        self.check_forbidden()
        if self.is_kw("LIMIT"):
            self.next()
            q.limit = self.int_value("LIMIT")
        if self.is_kw("OFFSET"):
            self.next()
            q.offset = self.int_value("OFFSET")
        self.check_forbidden()
        if self.peek() is not None:
            raise SoqlParseError(f"Unexpected token {self.peek().text!r}")
        return q

    def int_value(self, clause: str) -> int:
        tok = self.next()
        if tok.kind != "number" or "." in tok.text or tok.text.startswith("-"):
            raise SoqlParseError(f"{clause} must be a positive integer")
        return int(tok.text)

    def field_ref(self) -> FieldRef:
        tok = self.next()
        if tok.kind != "ident":
            raise SoqlParseError(f"Expected field name, got {tok.text!r}")
        if tok.upper in FORBIDDEN:
            raise SoqlParseError(FORBIDDEN[tok.upper], "forbidden_clause")
        return FieldRef(tuple(tok.text.split(".")))

    def expr(self):
        tok = self.peek()
        if tok is None:
            raise SoqlParseError("Unexpected end of query")
        if tok.text == "(":
            raise SoqlParseError("Child-relationship subqueries are not supported in the prototype",
                                 "subquery_not_supported")
        nxt = self.peek(1)
        if tok.kind == "ident" and nxt is not None and nxt.text == "(":
            func = tok.upper
            if func not in AGG_FUNCS:
                raise SoqlParseError(f"Function {tok.text} is not supported in the prototype",
                                     "function_not_supported")
            self.next()
            self.next()
            field = None
            if self.peek() and self.peek().text != ")":
                field = self.field_ref()
            self.expect_punct(")")
            if field is None and func != "COUNT":
                raise SoqlParseError(f"{func}() requires a field")
            return AggregateExpr(func, field)
        return self.field_ref()

    def select_item(self) -> SelectItem:
        e = self.expr()
        alias = None
        tok = self.peek()
        if tok is not None and tok.kind == "ident" and tok.upper not in {"FROM"} and "." not in tok.text:
            if not isinstance(e, AggregateExpr):
                raise SoqlParseError("Aliases are only allowed on aggregate expressions")
            alias = self.next().text
        return SelectItem(e, alias)

    def order_item(self) -> OrderItem:
        e = self.expr()
        direction, nulls = "ASC", None
        if self.is_kw("ASC", "DESC"):
            direction = self.next().upper
        if self.is_kw("NULLS"):
            self.next()
            if not self.is_kw("FIRST", "LAST"):
                raise SoqlParseError("Expected NULLS FIRST|LAST")
            nulls = self.next().upper
        return OrderItem(e, direction, nulls)

    def condition(self) -> Condition:
        items = [self.and_cond()]
        while self.is_kw("OR"):
            self.next()
            items.append(self.and_cond())
        return items[0] if len(items) == 1 else BoolOp("OR", tuple(items))

    def and_cond(self) -> Condition:
        items = [self.not_cond()]
        while self.is_kw("AND"):
            self.next()
            items.append(self.not_cond())
        return items[0] if len(items) == 1 else BoolOp("AND", tuple(items))

    def not_cond(self) -> Condition:
        if self.is_kw("NOT"):
            self.next()
            return NotOp(self.atom_cond())
        return self.atom_cond()

    def atom_cond(self) -> Condition:
        tok = self.peek()
        if tok is not None and tok.text == "(":
            self.next()
            c = self.condition()
            self.expect_punct(")")
            return c
        f = self.field_ref()
        op_tok = self.next()
        if op_tok.kind == "op":
            op = "!=" if op_tok.text == "<>" else op_tok.text
            return Comparison(f, op, self.literal())
        up = op_tok.upper
        if up == "LIKE":
            return Comparison(f, "LIKE", self.literal())
        if up == "IN":
            return Comparison(f, "IN", self.literal_list())
        if up == "NOT" and self.is_kw("IN"):
            self.next()
            return Comparison(f, "NOT IN", self.literal_list())
        if up in ("INCLUDES", "EXCLUDES"):
            raise SoqlParseError("INCLUDES/EXCLUDES are not supported in the prototype", "operator_not_supported")
        raise SoqlParseError(f"Unsupported operator {op_tok.text!r}", "operator_not_supported")

    def literal_list(self) -> tuple[Literal, ...]:
        self.expect_punct("(")
        if self.is_kw("SELECT"):
            raise SoqlParseError("Semi-join subqueries are not supported in the prototype",
                                 "subquery_not_supported")
        vals = [self.literal()]
        while self.peek() and self.peek().text == ",":
            self.next()
            vals.append(self.literal())
        self.expect_punct(")")
        return tuple(vals)

    def literal(self) -> Literal:
        tok = self.next()
        if tok.kind == "string":
            body = tok.text[1:-1]
            return Literal("string", re.sub(r"\\(.)", r"\1", body))
        if tok.kind == "number":
            return Literal("number", float(tok.text) if "." in tok.text else int(tok.text))
        if tok.kind == "date":
            return Literal("date", tok.text)
        if tok.kind == "datetime":
            return Literal("datetime", tok.text)
        if tok.kind == "dateN":
            name, n = tok.text.split(":")
            if name.upper() not in DATE_N_LITERALS:
                raise SoqlParseError(f"Unknown date literal {tok.text}")
            return Literal("date_literal", name.upper(), int(n))
        if tok.kind == "ident":
            up = tok.upper
            if up in ("TRUE", "FALSE"):
                return Literal("boolean", up == "TRUE")
            if up == "NULL":
                return Literal("null", None)
            if up in DATE_LITERALS:
                return Literal("date_literal", up)
        raise SoqlParseError(f"Invalid value {tok.text!r}")


def parse_soql(text: str) -> SoqlQuery:
    text = (text or "").strip()
    if not text:
        raise SoqlParseError("Query is empty")
    if len(text) > 20000:
        raise SoqlParseError("Query is too long", "too_long")
    return _Parser(tokenize(text)).parse()
