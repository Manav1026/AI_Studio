"""Deterministic, offline planner used for local development, CI and demos without an AI key.
It is intentionally simple — the real value is that it produces the SAME plan contract the LLM
providers do, so everything downstream (builder, validator, execution) is exercised identically."""
import json
import re
import time

from app.integrations.ai.base import AIProvider, AIRequest, AIResponse

_TIME = [
    (r"\bthis year\b|\bytd\b|\byear to date\b", "THIS_YEAR"), (r"\blast year\b", "LAST_YEAR"),
    (r"\bthis quarter\b", "THIS_QUARTER"), (r"\blast quarter\b", "LAST_QUARTER"),
    (r"\bnext quarter\b", "NEXT_QUARTER"), (r"\bthis month\b", "THIS_MONTH"),
    (r"\blast month\b", "LAST_MONTH"), (r"\bnext month\b", "NEXT_MONTH"), (r"\bthis week\b", "THIS_WEEK"),
    (r"\btoday\b", "TODAY"),
]
_OBJ_HINTS = [
    ("Opportunity", r"opportunit|deal|pipeline|revenue|bookings|sales|won|lost"),
    ("Case", r"\bcases?\b|ticket|support|escalat"),
    ("Contact", r"contact|people|person"),
    ("Lead", r"\bleads?\b"),
    ("Account", r"account|customer|compan|client"),
    ("User", r"\busers?\b|\breps?\b|salesperson"),
]


def _tokens(q: str) -> str:
    return " " + q.lower() + " "


class MockAIProvider(AIProvider):
    name = "mock"

    def complete(self, req: AIRequest) -> AIResponse:
        start = time.perf_counter()
        plan = self._plan(req.context.get("question", ""), req.context)
        content = json.dumps(plan)
        return AIResponse(content=content, provider=self.name, model="mock-planner-v1",
                          input_tokens=max(1, len(req.system + req.user) // 4),
                          output_tokens=max(1, len(content) // 4),
                          latency_ms=int((time.perf_counter() - start) * 1000))

    # --------------------------------------------------------------------------------------
    def _plan(self, question: str, ctx: dict) -> dict:
        q = _tokens(question)
        objects = {o["name"]: o for o in ctx.get("objects", [])}
        fields_of = {name: {f["name"]: f for f in o["fields"]} for name, o in objects.items()}

        # custom objects mentioned by label win
        root = None
        for name, o in objects.items():
            if name.endswith("__c") and re.search(r"\b" + re.escape(o["label"].lower()), q):
                root = name
        top_customers = re.search(r"(top|best|biggest|largest).{0,20}(customer|account|compan|client)", q)
        if root is None and top_customers and "Opportunity" in objects and re.search(r"revenue|opportunit|amount|deal|sales", q):
            root = "Opportunity"
        if root is None:  # an object named explicitly by its label wins (earliest mention)
            mentions = []
            for name, o in objects.items():
                labels = {o["label"].lower(), (o.get("label_plural") or "").lower()} - {""}
                for lab in labels:
                    m = re.search(r"\b" + re.escape(lab) + r"(?:s|es)?\b", q)
                    if m:
                        mentions.append((m.start(), name))
            if mentions:
                root = min(mentions)[1]
        if root is None:
            for name, pattern in _OBJ_HINTS:
                if name in objects and re.search(pattern, q):
                    root = name
                    break
        if root is None:
            root = next(iter(objects), "Account")
        fmap = fields_of.get(root, {})

        def has(f):
            return f in fmap

        n = re.search(r"\b(?:top|first|last|bottom)\s+(\d+)\b|\b(\d+)\s+(?:largest|biggest|top|records|rows)\b", q)
        limit = int(n.group(1) or n.group(2)) if n else None
        filters, aggs, group_by, order_by, fields = [], [], [], [], []

        date_field = next((f for f in ("CloseDate", "CreatedDate", "Start_Date__c") if has(f)), None)
        for pattern, literal in _TIME:
            if re.search(pattern, q) and date_field:
                filters.append({"field": date_field, "operator": "=", "value": literal})
                break
        m = re.search(r"last (\d+) days", q)
        if m and date_field:
            filters.append({"field": date_field, "operator": "=", "value": f"LAST_N_DAYS:{m.group(1)}"})

        if root == "Opportunity":
            if re.search(r"\bwon\b|closed won|revenue|bookings", q) and has("IsWon"):
                filters.append({"field": "IsWon", "operator": "=", "value": True})
            elif re.search(r"\blost\b", q) and has("StageName"):
                filters.append({"field": "StageName", "operator": "=", "value": "Closed Lost"})
            elif re.search(r"\bopen\b|pipeline", q) and has("IsClosed"):
                filters.append({"field": "IsClosed", "operator": "=", "value": False})
        if root == "Case" and re.search(r"\bopen\b|unresolved|active", q) and has("IsClosed"):
            filters.append({"field": "IsClosed", "operator": "=", "value": False})
        m = re.search(r"(?:over|above|greater than|more than|>)\s*\$?([\d,.]+)\s*(k|m)?", q)
        amount_field = next((f for f in ("Amount", "AnnualRevenue", "Budget__c") if has(f)), None)
        if m and amount_field:
            val = float(m.group(1).replace(",", "")) * {"k": 1e3, "m": 1e6}.get(m.group(2) or "", 1)
            filters.append({"field": amount_field, "operator": ">", "value": int(val)})
        # picklist value mentions, e.g. "high priority", "technology industry"
        for fname, f in fmap.items():
            for v in f.get("picklist_values", []):
                if re.search(r"\b" + re.escape(v.lower()) + r"\b", q) and not any(x["field"] == fname for x in filters):
                    if fname in ("StageName",) and any(x["field"] in ("IsWon", "IsClosed") for x in filters):
                        continue
                    filters.append({"field": fname, "operator": "=", "value": v})
        m = re.search(r"\b(?:at|for|from|of)\s+([A-Z][\w&]*(?:\s+[A-Z][\w&]*)*)", question)
        if m and root in ("Contact", "Opportunity", "Case") and "Account" in objects:
            filters.append({"field": "Account.Name", "operator": "LIKE", "value": f"%{m.group(1)}%"})

        by = re.search(r"\b(?:by|per|for each|grouped by)\s+([a-z ]+?)(?:\s+(?:this|last|next|in|over|with|where|for)\b|[?.!,]|$)",
                       question.lower())
        group_field = None
        if top_customers and root == "Opportunity":
            group_field = "Account.Name"
        elif by:
            phrase = by.group(1).strip()
            if re.search(r"customer|account|compan|client", phrase) and root != "Account":
                group_field = "Account.Name"
            elif re.search(r"owner|rep|salesperson", phrase) and has("OwnerId"):
                group_field = "Owner.Name"
            else:
                for fname, f in fmap.items():
                    if f.get("groupable") and (phrase in f["label"].lower() or phrase.rstrip("s") in fname.lower()):
                        group_field = fname
                        break
        is_count = re.search(r"how many|\bcount\b|number of", q)
        metric_field = amount_field if re.search(r"revenue|amount|value|total|sum|bookings|budget|pipeline|size|average|avg", q) else None
        if group_field:
            group_by = [group_field]
            if metric_field and not is_count:
                fn = "AVG" if re.search(r"average|avg|mean", q) else "SUM"
                aggs = [{"function": fn, "field": metric_field, "alias": "total" if fn == "SUM" else "average"}]
            else:
                aggs = [{"function": "COUNT", "field": "Id", "alias": "record_count"}]
            order_by = [{"field": aggs[0]["alias"], "direction": "DESC"}]
            limit = limit or (10 if top_customers else 50)
        elif is_count:
            aggs = [{"function": "COUNT", "field": "Id", "alias": "record_count"}]
        elif metric_field and re.search(r"total|sum|average|avg", q):
            fn = "AVG" if re.search(r"average|avg|mean", q) else "SUM"
            aggs = [{"function": fn, "field": metric_field, "alias": "total" if fn == "SUM" else "average"}]
        else:
            preferred = {
                "Opportunity": ["Name", "Account.Name", "Amount", "StageName", "CloseDate"],
                "Account": ["Name", "Industry", "Type", "AnnualRevenue", "BillingCity"],
                "Contact": ["Name", "Title", "Email", "Account.Name"],
                "Case": ["CaseNumber", "Subject", "Status", "Priority", "Account.Name"],
                "User": ["Name", "Email", "Title"],
                "Lead": ["Name", "Company", "Status", "Email"],
            }.get(root) or [f for f in list(fmap)[:6]]
            fields = [f for f in preferred if "." in f or has(f)]
            if top_customers or re.search(r"\b(top|largest|biggest|highest)\b", q):
                if amount_field:
                    order_by = [{"field": amount_field, "direction": "DESC"}]
            elif re.search(r"recent|latest|newest", q) and date_field:
                order_by = [{"field": date_field, "direction": "DESC"}]
            limit = limit or 25

        label = objects.get(root, {}).get("label_plural") or root
        explanation = self._explain(label, filters, aggs, group_by, order_by, limit)
        return {"intent": question.strip()[:200], "root_object": root,
                "objects": sorted({root} | ({"Account"} if any("Account." in x for x in fields + group_by +
                                                                [f["field"] for f in filters]) else set())),
                "fields": fields, "filters": filters, "aggregations": aggs, "group_by": group_by,
                "order_by": order_by, "limit": limit, "read_only": True, "explanation": explanation}

    @staticmethod
    def _explain(label, filters, aggs, group_by, order_by, limit) -> str:
        parts = []
        if aggs:
            a = aggs[0]
            what = "the number of records" if a["function"] == "COUNT" else f"the {a['function'].lower()} of {a['field']}"
            parts.append(f"Calculates {what} in {label}")
        else:
            parts.append(f"Lists {label}")
        if group_by:
            parts.append(f"grouped by {', '.join(group_by)}")
        if filters:
            parts.append("where " + " and ".join(
                f"{f['field']} {f['operator']} {str(f['value']).lower() if isinstance(f['value'], bool) else f['value']}"
                for f in filters))
        if order_by:
            parts.append(f"sorted by {order_by[0]['field']} {order_by[0]['direction'].lower()}")
        if limit:
            parts.append(f"limited to {limit} rows")
        return ", ".join(parts) + "."
