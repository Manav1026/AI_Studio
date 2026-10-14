"""Deterministic demo org: schema shaped exactly like Salesforce describe payloads + sample records.
Lets every layer (OAuth flow, sync, catalog, planning, validation, execution, MCP) run end-to-end
before a real Developer Edition / sandbox org is connected."""
import random
from datetime import date, timedelta

# (name, label, type, extra)
F = tuple
SCHEMA: dict[str, dict] = {
    "Account": {"label": "Account", "plural": "Accounts", "prefix": "001", "fields": [
        F(("Id", "Account ID", "id", {})), F(("Name", "Account Name", "string", {})),
        F(("Industry", "Industry", "picklist", {"values": ["Technology", "Finance", "Healthcare", "Retail",
                                                            "Manufacturing", "Energy"]})),
        F(("Type", "Account Type", "picklist", {"values": ["Customer", "Prospect", "Partner"]})),
        F(("AnnualRevenue", "Annual Revenue", "currency", {})),
        F(("NumberOfEmployees", "Employees", "int", {})),
        F(("BillingCity", "Billing City", "string", {})), F(("BillingState", "Billing State", "string", {})),
        F(("BillingCountry", "Billing Country", "string", {})),
        F(("Rating", "Account Rating", "picklist", {"values": ["Hot", "Warm", "Cold"]})),
        F(("OwnerId", "Owner ID", "reference", {"ref": ["User"], "rel": "Owner"})),
        F(("CreatedDate", "Created Date", "datetime", {})),
        F(("Customer_Tier__c", "Customer Tier", "picklist", {"values": ["Platinum", "Gold", "Silver"],
                                                              "custom": True})),
    ]},
    "Contact": {"label": "Contact", "plural": "Contacts", "prefix": "003", "fields": [
        F(("Id", "Contact ID", "id", {})), F(("FirstName", "First Name", "string", {})),
        F(("LastName", "Last Name", "string", {})), F(("Name", "Full Name", "string", {"nofilter_group": True})),
        F(("Email", "Email", "email", {})), F(("Phone", "Business Phone", "phone", {})),
        F(("Title", "Title", "string", {})),
        F(("AccountId", "Account ID", "reference", {"ref": ["Account"], "rel": "Account", "child": "Contacts"})),
        F(("OwnerId", "Owner ID", "reference", {"ref": ["User"], "rel": "Owner"})),
        F(("LeadSource", "Lead Source", "picklist", {"values": ["Web", "Referral", "Partner", "Event"]})),
        F(("CreatedDate", "Created Date", "datetime", {})),
    ]},
    "Opportunity": {"label": "Opportunity", "plural": "Opportunities", "prefix": "006", "fields": [
        F(("Id", "Opportunity ID", "id", {})), F(("Name", "Name", "string", {})),
        F(("AccountId", "Account ID", "reference", {"ref": ["Account"], "rel": "Account",
                                                     "child": "Opportunities"})),
        F(("Amount", "Amount", "currency", {})), F(("CloseDate", "Close Date", "date", {})),
        F(("StageName", "Stage", "picklist", {"values": ["Prospecting", "Qualification", "Proposal",
                                                          "Negotiation", "Closed Won", "Closed Lost"]})),
        F(("Probability", "Probability (%)", "percent", {})), F(("IsWon", "Won", "boolean", {})),
        F(("IsClosed", "Closed", "boolean", {})),
        F(("Type", "Opportunity Type", "picklist", {"values": ["New Business", "Existing Business",
                                                                "Renewal"]})),
        F(("LeadSource", "Lead Source", "picklist", {"values": ["Web", "Referral", "Partner", "Event"]})),
        F(("OwnerId", "Owner ID", "reference", {"ref": ["User"], "rel": "Owner"})),
        F(("CreatedDate", "Created Date", "datetime", {})),
    ]},
    "Case": {"label": "Case", "plural": "Cases", "prefix": "500", "fields": [
        F(("Id", "Case ID", "id", {})), F(("CaseNumber", "Case Number", "string", {})),
        F(("Subject", "Subject", "string", {})),
        F(("Status", "Status", "picklist", {"values": ["New", "Working", "Escalated", "Closed"]})),
        F(("Priority", "Priority", "picklist", {"values": ["High", "Medium", "Low"]})),
        F(("Origin", "Case Origin", "picklist", {"values": ["Phone", "Email", "Web"]})),
        F(("IsClosed", "Closed", "boolean", {})),
        F(("AccountId", "Account ID", "reference", {"ref": ["Account"], "rel": "Account", "child": "Cases"})),
        F(("ContactId", "Contact ID", "reference", {"ref": ["Contact"], "rel": "Contact", "child": "Cases"})),
        F(("OwnerId", "Owner ID", "reference", {"ref": ["User"], "rel": "Owner"})),
        F(("CreatedDate", "Created Date", "datetime", {})),
    ]},
    "User": {"label": "User", "plural": "Users", "prefix": "005", "fields": [
        F(("Id", "User ID", "id", {})), F(("Name", "Full Name", "string", {})),
        F(("Email", "Email", "email", {})), F(("Title", "Title", "string", {})),
        F(("Department", "Department", "string", {})), F(("IsActive", "Active", "boolean", {})),
    ]},
    "Project__c": {"label": "Project", "plural": "Projects", "prefix": "a01", "custom": True, "fields": [
        F(("Id", "Record ID", "id", {})), F(("Name", "Project Name", "string", {})),
        F(("Account__c", "Account", "reference", {"ref": ["Account"], "rel": "Account__r",
                                                   "child": "Projects__r", "custom": True,
                                                   "master_detail": True})),
        F(("Status__c", "Status", "picklist", {"values": ["Planned", "Active", "Completed"], "custom": True})),
        F(("Budget__c", "Budget", "currency", {"custom": True})),
        F(("Start_Date__c", "Start Date", "date", {"custom": True})),
    ]},
}

_GROUPABLE = {"id", "string", "picklist", "reference", "boolean", "date", "email", "phone", "int"}
_AGGREGATABLE = {"currency", "double", "int", "percent", "date", "datetime", "string", "picklist", "id",
                 "reference", "email", "phone"}


def describe_global() -> list[dict]:
    return [{"name": n, "label": o["label"], "labelPlural": o["plural"], "keyPrefix": o["prefix"],
             "custom": o.get("custom", False), "queryable": True, "deprecatedAndHidden": False}
            for n, o in SCHEMA.items()]


def describe(name: str) -> dict:
    o = SCHEMA[name]
    fields, children = [], []
    for fname, label, ftype, extra in o["fields"]:
        fields.append({
            "name": fname, "label": label, "type": ftype, "referenceTo": extra.get("ref", []),
            "relationshipName": extra.get("rel"), "custom": extra.get("custom", False),
            "filterable": not extra.get("nofilter_group", False), "sortable": ftype != "textarea",
            "groupable": ftype in _GROUPABLE and not extra.get("nofilter_group", False),
            "aggregatable": ftype in _AGGREGATABLE, "nillable": fname != "Id",
            "relationshipOrder": 0 if extra.get("master_detail") else None,
            "cascadeDelete": bool(extra.get("master_detail")),
            "picklistValues": [{"value": v, "label": v, "active": True} for v in extra.get("values", [])],
        })
    for other, oo in SCHEMA.items():
        for fname, _, _, extra in oo["fields"]:
            if name in extra.get("ref", []) and extra.get("child"):
                children.append({"childSObject": other, "field": fname, "relationshipName": extra["child"],
                                 "cascadeDelete": bool(extra.get("master_detail"))})
    return {"name": name, "label": o["label"], "labelPlural": o["plural"], "keyPrefix": o["prefix"],
            "custom": o.get("custom", False), "queryable": True, "fields": fields, "childRelationships": children}


def _id(prefix: str, n: int) -> str:
    return f"{prefix}{'0' * (15 - len(prefix) - len(str(n)))}{n}"


def build_records(today: date | None = None) -> dict[str, list[dict]]:
    today = today or date.today()
    rnd = random.Random(42)
    users = [{"Id": _id("005", i + 1), "Name": n, "Email": f"{n.split()[0].lower()}@demo.example",
              "Title": t, "Department": "Sales", "IsActive": True}
             for i, (n, t) in enumerate([("Priya Shah", "Account Executive"), ("Marcus Lee", "Sales Manager"),
                                         ("Elena Garcia", "Account Executive"), ("Tom Becker", "SDR")])]
    names = ["Acme Corp", "Globex", "Initech", "Umbrella Health", "Stark Industries", "Wayne Enterprises",
             "Soylent Foods", "Hooli", "Vandelay Imports", "Wonka Retail", "Cyberdyne Systems", "Tyrell Energy",
             "Massive Dynamic", "Oscorp", "Pied Piper", "Aperture Labs", "Nakatomi Trading", "Gringotts Finance",
             "Monarch Solutions", "Blue Sun Retail", "Dunder Mifflin", "Los Pollos Group", "Prestige Worldwide",
             "Bluth Company", "Sterling Cooper"]
    cities = [("Iselin", "NJ"), ("New York", "NY"), ("Austin", "TX"), ("Chicago", "IL"), ("Seattle", "WA"),
              ("Boston", "MA"), ("Denver", "CO"), ("Atlanta", "GA")]
    industries = ["Technology", "Finance", "Healthcare", "Retail", "Manufacturing", "Energy"]
    accounts = []
    for i, n in enumerate(names):
        city, state = rnd.choice(cities)
        accounts.append({
            "Id": _id("001", i + 1), "Name": n, "Industry": rnd.choice(industries),
            "Type": rnd.choice(["Customer", "Customer", "Prospect", "Partner"]),
            "AnnualRevenue": rnd.randrange(2, 900) * 1_000_000, "NumberOfEmployees": rnd.randrange(20, 50000),
            "BillingCity": city, "BillingState": state, "BillingCountry": "USA",
            "Rating": rnd.choice(["Hot", "Warm", "Cold"]), "OwnerId": rnd.choice(users)["Id"],
            "CreatedDate": f"{today.year - rnd.randrange(0, 4)}-0{rnd.randrange(1, 9)}-1{rnd.randrange(0, 9)}T10:00:00.000+0000",
            "Customer_Tier__c": rnd.choice(["Platinum", "Gold", "Silver"]),
        })
    first = ["Ava", "Liam", "Noah", "Mia", "Zoe", "Ethan", "Arjun", "Sofia", "Leo", "Nina", "Omar", "Grace"]
    last = ["Patel", "Smith", "Kim", "Nguyen", "Brown", "Singh", "Lopez", "Cohen", "Rossi", "Okafor"]
    titles = ["CFO", "VP Sales", "IT Director", "Procurement Manager", "CTO", "Operations Lead"]
    contacts = []
    for i in range(70):
        fn, ln, acct = rnd.choice(first), rnd.choice(last), rnd.choice(accounts)
        contacts.append({
            "Id": _id("003", i + 1), "FirstName": fn, "LastName": ln, "Name": f"{fn} {ln}",
            "Email": f"{fn.lower()}.{ln.lower()}@{acct['Name'].split()[0].lower()}.example",
            "Phone": f"(732) 555-{1000 + i}", "Title": rnd.choice(titles), "AccountId": acct["Id"],
            "OwnerId": acct["OwnerId"], "LeadSource": rnd.choice(["Web", "Referral", "Partner", "Event"]),
            "CreatedDate": f"{today.year}-0{rnd.randrange(1, 9)}-0{rnd.randrange(1, 9)}T09:00:00.000+0000",
        })
    stages = ["Prospecting", "Qualification", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]
    prob = {"Prospecting": 10, "Qualification": 20, "Proposal": 50, "Negotiation": 75, "Closed Won": 100,
            "Closed Lost": 0}
    opps = []
    for i in range(160):
        acct, stage = rnd.choice(accounts), rnd.choice(stages)
        close = today + timedelta(days=rnd.randrange(-500, 180))
        opps.append({
            "Id": _id("006", i + 1), "Name": f"{acct['Name']} - {rnd.choice(['Platform', 'Expansion', 'Renewal', 'Pilot', 'Services'])}",
            "AccountId": acct["Id"], "Amount": rnd.randrange(5, 400) * 1000, "CloseDate": close.isoformat(),
            "StageName": stage, "Probability": prob[stage], "IsWon": stage == "Closed Won",
            "IsClosed": stage.startswith("Closed"),
            "Type": rnd.choice(["New Business", "Existing Business", "Renewal"]),
            "LeadSource": rnd.choice(["Web", "Referral", "Partner", "Event"]), "OwnerId": acct["OwnerId"],
            "CreatedDate": (close - timedelta(days=rnd.randrange(20, 200))).isoformat() + "T12:00:00.000+0000",
        })
    cases = []
    for i in range(60):
        c = rnd.choice(contacts)
        status = rnd.choice(["New", "Working", "Escalated", "Closed", "Closed"])
        cases.append({
            "Id": _id("500", i + 1), "CaseNumber": f"{1000 + i:08d}",
            "Subject": rnd.choice(["Login issue", "Billing question", "Integration error", "Feature request",
                                   "Data export failing", "Performance degradation"]),
            "Status": status, "Priority": rnd.choice(["High", "Medium", "Low"]),
            "Origin": rnd.choice(["Phone", "Email", "Web"]), "IsClosed": status == "Closed",
            "AccountId": c["AccountId"], "ContactId": c["Id"], "OwnerId": rnd.choice(users)["Id"],
            "CreatedDate": (today - timedelta(days=rnd.randrange(0, 120))).isoformat() + "T08:30:00.000+0000",
        })
    projects = []
    for i in range(18):
        acct = rnd.choice(accounts)
        projects.append({
            "Id": _id("a01", i + 1), "Name": f"{acct['Name']} Rollout {i + 1}", "Account__c": acct["Id"],
            "Status__c": rnd.choice(["Planned", "Active", "Completed"]), "Budget__c": rnd.randrange(20, 500) * 1000,
            "Start_Date__c": (today - timedelta(days=rnd.randrange(0, 365))).isoformat(),
        })
    return {"User": users, "Account": accounts, "Contact": contacts, "Opportunity": opps, "Case": cases,
            "Project__c": projects}
