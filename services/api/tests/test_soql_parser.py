import pytest
from app.domain.soql.ast import to_soql
from app.domain.soql.parser import SoqlParseError, parse_soql


def test_parses_aggregate_with_relationship():
    q = parse_soql("SELECT Account.Name, SUM(Amount) total FROM Opportunity WHERE CloseDate = THIS_YEAR "
                   "AND IsWon = true GROUP BY Account.Name ORDER BY SUM(Amount) DESC NULLS LAST LIMIT 10")
    assert q.from_object == "Opportunity" and q.limit == 10 and q.has_aggregates
    assert to_soql(q).startswith("SELECT Account.Name, SUM(Amount) total FROM Opportunity WHERE")


@pytest.mark.parametrize("soql,code", [
    ("DELETE FROM Account", "not_select"),
    ("SELECT Id FROM Account FOR UPDATE", "forbidden_clause"),
    ("SELECT Id FROM Account; SELECT Id FROM Contact", "multiple_statements"),
    ("SELECT Id, (SELECT Id FROM Contacts) FROM Account", "subquery_not_supported"),
    ("SELECT Id FROM Account WHERE Id IN (SELECT AccountId FROM Contact)", "subquery_not_supported"),
    ("SELECT CALENDAR_YEAR(CloseDate) FROM Opportunity", "function_not_supported"),
])
def test_rejects_unsafe_or_unsupported(soql, code):
    with pytest.raises(SoqlParseError) as e:
        parse_soql(soql)
    assert e.value.code == code


def test_string_escaping_roundtrip():
    q = parse_soql("SELECT Id FROM Account WHERE Name = 'O\\'Reilly' AND Name LIKE '%x%'")
    assert "'O\\'Reilly'" in to_soql(q)


def test_date_n_literal_and_in():
    q = parse_soql("SELECT Id FROM Case WHERE CreatedDate = LAST_N_DAYS:30 AND Priority IN ('High','Medium')")
    assert "LAST_N_DAYS:30" in to_soql(q) and "IN ('High', 'Medium')" in to_soql(q)
