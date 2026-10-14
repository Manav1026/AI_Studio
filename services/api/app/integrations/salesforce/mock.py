"""In-process mock connector. It executes the *same* validated SOQL the live connector would send,
using the shared parser, so the query path is exercised for real."""
import fnmatch
from datetime import date, datetime

from app.domain.soql.ast import AggregateExpr, BoolOp, Comparison, FieldRef, NotOp, SoqlQuery
from app.domain.soql.dates import date_literal_range
from app.domain.soql.parser import parse_soql
from app.integrations.salesforce import mock_data
from app.integrations.salesforce.base import (
    OrgIdentity,
    QueryResult,
    SalesforceConnector,
    SalesforceError,
)

MOCK_ORG_ID = "00DMOCK0000000001"
MOCK_INSTANCE = "https://mock-org.my.salesforce.com"


class MockSalesforceConnector(SalesforceConnector):
    def __init__(self, today: date | None = None):
        self.today = today or date.today()
        self.data = mock_data.build_records(self.today)
        self._by_id = {r["Id"]: (obj, r) for obj, rows in self.data.items() for r in rows}

    def get_identity(self) -> OrgIdentity:
        return OrgIdentity(org_id=MOCK_ORG_ID, user_id="005000000000001", username="demo.user@mock-org.example",
                           instance_url=MOCK_INSTANCE, org_name="Demo Org (mock)")

    def describe_global(self) -> list[dict]:
        return mock_data.describe_global()

    def describe_object(self, name: str) -> dict:
        match = next((n for n in mock_data.SCHEMA if n.lower() == name.lower()), None)
        if match is None:
            raise SalesforceError(f"sObject type '{name}' is not supported.", status=404, error_code="NOT_FOUND")
        return mock_data.describe(match)

    def get_limits(self) -> dict:
        return {"DailyApiRequests": {"Max": 15000, "Remaining": 14873}}

    # --- evaluation -----------------------------------------------------------------------
    def _resolve(self, obj: str, rec: dict, path: tuple[str, ...]):
        schema = mock_data.SCHEMA
        cur_obj, cur = obj, rec
        for i, part in enumerate(path):
            fields = {f[0].lower(): f for f in schema[cur_obj]["fields"]}
            if i == len(path) - 1:
                f = fields.get(part.lower())
                return cur.get(f[0]) if f else None
            ref = next((f for f in schema[cur_obj]["fields"] if (f[3].get("rel") or "").lower() == part.lower()), None)
            if ref is None or cur.get(ref[0]) is None:
                return None
            target = self._by_id.get(cur[ref[0]])
            if target is None:
                return None
            cur_obj, cur = target
        return None

    def _to_cmp(self, v):
        if isinstance(v, str) and len(v) >= 10 and v[4] == "-" and v[7] == "-":
            try:
                return date.fromisoformat(v[:10])
            except ValueError:
                return v
        return v

    def _eval(self, obj: str, rec: dict, cond) -> bool:
        if isinstance(cond, BoolOp):
            results = (self._eval(obj, rec, c) for c in cond.items)
            return all(results) if cond.op == "AND" else any(results)
        if isinstance(cond, NotOp):
            return not self._eval(obj, rec, cond.item)
        assert isinstance(cond, Comparison)
        actual = self._to_cmp(self._resolve(obj, rec, cond.field.path))
        if isinstance(cond.value, tuple):
            vals = [self._lit(v) for v in cond.value]
            hit = any(self._equal(actual, v) for v in vals)
            return hit if cond.op == "IN" else not hit
        lit = cond.value
        if lit.kind == "date_literal":
            start, end = date_literal_range(lit.value, lit.n, self.today)
            if actual is None:
                return False
            d = actual if isinstance(actual, date) else self._to_cmp(str(actual))
            return {"=": start <= d <= end, "!=": not (start <= d <= end), "<": d < start, ">": d > end,
                    "<=": d <= end, ">=": d >= start}[cond.op]
        expected = self._lit(lit)
        if cond.op == "=":
            return self._equal(actual, expected)
        if cond.op == "!=":
            return not self._equal(actual, expected)
        if cond.op == "LIKE":
            pattern = str(expected).lower().replace("%", "*").replace("_", "?")
            return actual is not None and fnmatch.fnmatch(str(actual).lower(), pattern)
        if actual is None or expected is None:
            return False
        try:
            return {"<": actual < expected, ">": actual > expected, "<=": actual <= expected,
                    ">=": actual >= expected}[cond.op]
        except TypeError:
            return False

    def _lit(self, lit):
        if lit.kind in ("date", "datetime"):
            return date.fromisoformat(lit.value[:10])
        return lit.value

    @staticmethod
    def _equal(a, b) -> bool:
        if isinstance(a, str) and isinstance(b, str):
            return a.lower() == b.lower()  # SOQL string comparison is case-insensitive
        return a == b

    def _nest(self, obj: str, rec: dict, path: tuple[str, ...], out: dict) -> None:
        """Shape results like Salesforce: relationship fields are nested objects."""
        if len(path) == 1:
            out[path[0]] = self._resolve(obj, rec, path)
            return
        node = out.setdefault(path[0], {"attributes": {"type": "?"}})
        if node is None:
            return
        val = self._resolve(obj, rec, path)
        cur = node
        for p in path[1:-1]:
            cur = cur.setdefault(p, {"attributes": {"type": "?"}})
        cur[path[-1]] = val

    def query(self, soql: str, *, max_records: int = 2000) -> QueryResult:
        q: SoqlQuery = parse_soql(soql)
        obj = next((n for n in mock_data.SCHEMA if n.lower() == q.from_object.lower()), None)
        if obj is None:
            raise SalesforceError(f"sObject type '{q.from_object}' is not supported.", status=400,
                                  error_code="INVALID_TYPE")
        rows = [r for r in self.data.get(obj, []) if q.where is None or self._eval(obj, r, q.where)]
        if q.has_aggregates or q.group_by:
            out = self._aggregate(obj, rows, q)
        else:
            out = []
            for r in rows:
                rec = {"attributes": {"type": obj, "url": f"/services/data/v62.0/sobjects/{obj}/{r['Id']}"}}
                for item in q.select:
                    self._nest(obj, r, item.expr.path, rec)
                rec["__sort"] = r
                out.append(rec)
            for o in reversed(q.order_by):
                out.sort(key=lambda rec: self._sort_key(self._resolve(obj, rec["__sort"], o.expr.path)),
                         reverse=o.direction == "DESC")
            for rec in out:
                rec.pop("__sort", None)
        total = len(out)
        if q.offset:
            out = out[q.offset:]
        if q.limit is not None:
            out = out[: q.limit]
        return QueryResult(records=out[:max_records], total_size=total)

    @staticmethod
    def _sort_key(v):
        if v is None:
            return (1, "")
        if isinstance(v, (int, float)):
            return (0, v)
        return (0, str(v).lower()) if not isinstance(v, (date, datetime)) else (0, v.isoformat())

    def _aggregate(self, obj: str, rows: list[dict], q: SoqlQuery) -> list[dict]:
        groups: dict[tuple, list[dict]] = {}
        for r in rows:
            key = tuple(self._resolve(obj, r, g.path) for g in q.group_by)
            groups.setdefault(key, []).append(r)
        if not q.group_by and not groups:
            groups[()] = []
        out = []
        for key, members in groups.items():
            rec = {"attributes": {"type": "AggregateResult"}}
            expr_idx = 0
            for item in q.select:
                if isinstance(item.expr, FieldRef):
                    idx = [g.dotted.lower() for g in q.group_by].index(item.expr.dotted.lower())
                    rec[item.expr.path[-1]] = key[idx]
                else:
                    alias = item.alias or f"expr{expr_idx}"
                    expr_idx += 0 if item.alias else 1
                    rec[alias] = self._agg_value(obj, members, item.expr)
            rec["__members"] = members
            out.append(rec)
        for o in reversed(q.order_by):
            def k(rec, o=o):
                if isinstance(o.expr, AggregateExpr):
                    return self._sort_key(self._agg_value(obj, rec["__members"], o.expr))
                return self._sort_key(rec.get(o.expr.path[-1]))
            out.sort(key=k, reverse=o.direction == "DESC")
        for rec in out:
            rec.pop("__members", None)
        return out

    def _agg_value(self, obj, members, agg: AggregateExpr):
        if agg.field is None:
            return len(members)
        vals = [self._resolve(obj, m, agg.field.path) for m in members]
        vals = [v for v in vals if v is not None]
        if agg.func == "COUNT":
            return len(vals)
        if agg.func == "COUNT_DISTINCT":
            return len(set(vals))
        if not vals:
            return None
        if agg.func == "SUM":
            return sum(vals)
        if agg.func == "AVG":
            return round(sum(vals) / len(vals), 2)
        return min(vals) if agg.func == "MIN" else max(vals)
