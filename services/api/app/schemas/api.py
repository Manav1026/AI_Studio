"""Public API contracts (v1). Exported to packages/contracts/openapi.json for the web client."""
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, EmailStr, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class DevLoginIn(BaseModel):
    email: EmailStr
    display_name: str | None = None


class MeOut(BaseModel):
    user_id: str
    email: str
    display_name: str | None
    tenant_id: str
    tenant_name: str
    role: str
    auth_mode: str
    salesforce_mode: str
    ai_provider: str


class ConnectionOut(BaseModel):
    id: str
    org_id: str
    org_name: str | None
    instance_url: str
    sf_username: str | None
    mode: str
    status: str
    scopes: list[str]
    api_version: str
    last_sync_at: str | None
    catalog_version: str | None
    latest_sync: dict | None = None


class StartConnectionOut(BaseModel):
    authorization_url: str
    state_expires_in: int


class PlanIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    connection_id: str | None = None
    use_templates: bool = True


class ValidateIn(BaseModel):
    soql: str = Field(min_length=6, max_length=20000)
    connection_id: str | None = None


class ExecuteIn(BaseModel):
    execution_id: str | None = None
    soql: str | None = Field(default=None, max_length=20000)
    connection_id: str | None = None


class SavedQueryIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str | None = None
    execution_id: str | None = None
    soql: str | None = None
    parameters_schema: dict[str, Any] | None = None
    visibility: Literal["private", "tenant"] = "private"
    question_examples: list[str] | None = None
    connection_id: str | None = None
    auto_parameterize: bool = True


class SavedQueryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    template: str | None = None
    parameters_schema: dict[str, Any] | None = None
    visibility: Literal["private", "tenant"] | None = None
    question_examples: list[str] | None = None


class SavedExecuteIn(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
