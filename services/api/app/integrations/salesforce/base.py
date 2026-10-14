"""Salesforce connector contract. Everything Salesforce-specific (API versions, error shapes,
token refresh) lives behind this interface. Application services never call Salesforce directly."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OrgIdentity:
    org_id: str
    user_id: str
    username: str
    instance_url: str
    org_name: str | None = None


@dataclass
class QueryResult:
    records: list[dict[str, Any]]
    total_size: int
    done: bool = True
    raw: dict = field(default_factory=dict)


class SalesforceError(Exception):
    def __init__(self, message: str, *, status: int | None = None, error_code: str | None = None):
        super().__init__(message)
        self.status = status
        self.error_code = error_code


class SalesforceAuthError(SalesforceError):
    pass


class SalesforceConnector(ABC):
    @abstractmethod
    def get_identity(self) -> OrgIdentity: ...

    @abstractmethod
    def describe_global(self) -> list[dict]:
        """Returns Salesforce describeGlobal 'sobjects' entries."""

    @abstractmethod
    def describe_object(self, name: str) -> dict:
        """Returns Salesforce sObject describe payload."""

    @abstractmethod
    def query(self, soql: str, *, max_records: int = 2000) -> QueryResult: ...

    @abstractmethod
    def get_limits(self) -> dict: ...
