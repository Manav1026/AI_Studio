"""Central configuration. Every environment (local, CI, staging, prod) uses the same
settings interface; only the values / secret backend change."""
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), extra="ignore")

    app_env: Literal["local", "test", "dev", "staging", "production"] = "local"
    app_name: str = "Salesforce AI Workspace"
    app_secret_key: str = Field(default="change-me-in-env", min_length=8)
    session_ttl_minutes: int = 60 * 12
    auth_mode: Literal["dev", "oidc"] = "dev"

    # URLs
    web_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:3000"

    # Primary database + cache
    database_url: str = "postgresql+psycopg://sfai:sfai@localhost:5432/sfai"
    db_pool_size: int = 10
    redis_url: str = "redis://localhost:6379/0"

    # Secrets: Fernet key for the encrypted credential store (prototype backend)
    encryption_key: str = ""

    # Salesforce
    salesforce_mode: Literal["mock", "live"] = "mock"
    sf_client_id: str = ""
    sf_client_secret: str = ""
    sf_login_url: str = "https://login.salesforce.com"
    sf_api_version: str = "v62.0"
    sf_callback_url: str = "http://localhost:8000/api/v1/salesforce/oauth/callback"
    sf_scopes: str = "api refresh_token openid"
    sf_sync_objects: str = (
        "Account,Contact,Opportunity,Lead,Case,User,Campaign,Task,Event,Product2,"
        "OpportunityLineItem,Contract,Order"
    )
    sf_sync_include_custom: bool = True
    sf_sync_max_objects: int = 200
    sf_query_timeout_seconds: float = 30.0

    # Background jobs
    sync_mode: Literal["queue", "inline"] = "queue"
    rq_queue_name: str = "metadata-sync"

    # AI gateway
    ai_provider: Literal["mock", "openai", "anthropic"] = "mock"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    ai_timeout_seconds: float = 45.0
    ai_max_retries: int = 2

    # Query governance
    query_default_limit: int = 50
    query_max_limit: int = 200
    query_max_fields: int = 50
    query_max_conditions: int = 20
    query_max_relationship_depth: int = 3
    policy_blocked_objects: str = ""
    policy_blocked_fields: str = ""  # e.g. "Contact.SSN__c,*.Password__c"
    result_cache_ttl_seconds: int = 60
    catalog_cache_ttl_seconds: int = 600
    template_match_threshold: float = 0.6

    # Rate limits (per user per minute)
    rate_limit_query_per_minute: int = 30
    rate_limit_ai_per_minute: int = 15

    # Observability
    log_level: str = "INFO"
    log_json: bool = True
    otel_enabled: bool = False
    otel_exporter: Literal["console", "otlp"] = "console"
    otel_service_name: str = "sfai-api"

    # MCP
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8001
    mcp_public_url: str = "http://localhost:8001/mcp"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sync_object_list(self) -> list[str]:
        return [o.strip() for o in self.sf_sync_objects.split(",") if o.strip()]

    @property
    def blocked_objects(self) -> set[str]:
        return {o.strip().lower() for o in self.policy_blocked_objects.split(",") if o.strip()}

    @property
    def blocked_fields(self) -> set[str]:
        return {o.strip().lower() for o in self.policy_blocked_fields.split(",") if o.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
