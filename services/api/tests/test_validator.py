import pytest
from app.domain.catalog_view import CatalogView, FieldInfo, ObjectInfo
from app.domain.policy import QueryPolicy
from app.domain.query_plan import QueryPlan, plan_to_soql
from app.domain.soql.validator import validate_soql


@pytest.fixture
def view():
    acc = ObjectInfo("Account", "Account", fields={
        "id": FieldInfo("Id", "ID", "id", groupable=True), "name": FieldInfo("Name", "Name", "string", groupable=True),
        "annualrevenue": FieldInfo("AnnualRevenue", "Annual Revenue", "currency"),
        "ssn__c": FieldInfo("SSN__c", "SSN", "string")})
    opp = ObjectInfo("Opportunity", "Opportunity", fields={
        "id": FieldInfo("Id", "ID", "id", groupable=True), "name": FieldInfo("Name", "Name", "string", groupable=True),
        "amount": FieldInfo("Amount", "Amount", "currency", aggregatable=True),
        "closedate": FieldInfo("CloseDate", "Close Date", "date", groupable=True),
        "iswon": FieldInfo("IsWon", "Won", "boolean", groupable=True),
        "accountid": FieldInfo("AccountId", "Account ID", "reference", reference_to=["Account"],
                               relationship_name="Account", groupable=True)})
    return CatalogView("c1", "v1", {"account": acc, "opportunity": opp})


def pol(**kw):
    return QueryPolicy(**kw)


def test_valid_aggregate(view):
    r = validate_soql("SELECT Account.Name, SUM(Amount) total FROM Opportunity WHERE CloseDate = THIS_YEAR "
                      "GROUP BY Account.Name ORDER BY SUM(Amount) DESC LIMIT 10", view, pol())
    assert r.valid, r.issues
    assert r.referenced_objects == ["Account", "Opportunity"]


@pytest.mark.parametrize("soql,code", [
    ("SELECT Id FROM Lead", "unknown_object"),
    ("SELECT Foo FROM Account", "unknown_field"),
    ("SELECT Owner.Name FROM Opportunity", "invalid_relationship_path"),
    ("SELECT SUM(Name) FROM Opportunity", "aggregate_type_mismatch"),
    ("SELECT Id FROM Opportunity WHERE Amount = 'abc'", "operator_type_mismatch"),
    ("SELECT Id FROM Opportunity WHERE CloseDate = 5", "operator_type_mismatch"),
    ("SELECT Name, SUM(Amount) FROM Opportunity", "ungrouped_field"),
    ("SELECT Amount FROM Opportunity GROUP BY Amount", "field_not_groupable"),
])
def test_rejections(view, soql, code):
    r = validate_soql(soql, view, pol())
    assert not r.valid
    assert code in [i.code for i in r.issues]


def test_limit_injected_and_capped(view):
    r = validate_soql("SELECT Id FROM Account", view, pol(default_limit=50))
    assert r.valid and r.normalized_soql.endswith("LIMIT 50")
    r = validate_soql("SELECT Id FROM Account LIMIT 5000", view, pol(max_limit=200))
    assert r.valid and r.normalized_soql.endswith("LIMIT 200")


def test_policy_blocks_field_and_object(view):
    r = validate_soql("SELECT SSN__c FROM Account LIMIT 1", view, pol(blocked_fields={"*.ssn__c"}))
    assert "field_blocked_by_policy" in [i.code for i in r.issues]
    r = validate_soql("SELECT Id FROM Account LIMIT 1", view, pol(blocked_objects={"account"}))
    assert "object_blocked_by_policy" in [i.code for i in r.issues]


def test_plan_compiles_to_valid_soql(view):
    plan = QueryPlan.model_validate({
        "intent": "top customers", "root_object": "Opportunity", "fields": [],
        "filters": [{"field": "Opportunity.CloseDate", "operator": "THIS_YEAR"},
                    {"field": "IsWon", "operator": "=", "value": True}],
        "aggregation": {"function": "SUM", "field": "Opportunity.Amount", "alias": "total"},
        "group_by": ["Account.Name"], "order_by": [{"field": "total", "direction": "DESC"}], "limit": 10})
    soql = plan_to_soql(plan, view)
    assert soql == ("SELECT Account.Name, SUM(Amount) total FROM Opportunity WHERE CloseDate = THIS_YEAR AND "
                    "IsWon = true GROUP BY Account.Name ORDER BY SUM(Amount) DESC NULLS LAST LIMIT 10")
    assert validate_soql(soql, view, pol()).valid


def test_plan_values_are_escaped(view):
    plan = QueryPlan(intent="x", root_object="Account", fields=["Name"],
                     filters=[{"field": "Name", "operator": "=", "value": "x' OR Name != '"}], limit=5)
    soql = plan_to_soql(plan, view)
    assert "Name = 'x\\' OR Name != \\''" in soql
    r = validate_soql(soql, view, pol())
    assert r.valid and len(r.referenced_fields) == 1
