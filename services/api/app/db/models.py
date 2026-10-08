"""System-of-record schema (PostgreSQL). Every tenant-owned table carries tenant_id so the
one-org prototype is structurally multi-tenant from day one."""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPk, utcnow


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)


class Tenant(UUIDPk, Timestamps, Base):
    __tablename__ = "tenants"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)


class TenantUser(Base):
    __tablename__ = "tenant_users"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)  # owner|admin|member
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CredentialSecret(UUIDPk, Timestamps, Base):
    """Prototype secret backend: encrypted at rest. auth_ref on connections points here.
    In production the SecretStore interface is backed by a cloud secrets manager instead."""
    __tablename__ = "credential_secrets"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SalesforceConnection(UUIDPk, Timestamps, Base):
    __tablename__ = "salesforce_connections"
    __table_args__ = (UniqueConstraint("tenant_id", "org_id", name="uq_sf_conn_tenant_org"),)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    org_id: Mapped[str] = mapped_column(String(18), nullable=False)
    org_name: Mapped[str | None] = mapped_column(String(255))
    instance_url: Mapped[str] = mapped_column(String(500), nullable=False)
    sf_username: Mapped[str | None] = mapped_column(String(320))
    sf_user_id: Mapped[str | None] = mapped_column(String(18))
    mode: Mapped[str] = mapped_column(String(10), default="live", nullable=False)  # live|mock
    api_version: Mapped[str] = mapped_column(String(10), nullable=False)
    auth_ref: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("credential_secrets.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # active|error|revoked
    scopes: Mapped[list] = mapped_column(JSONB, default=list)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    catalog_version: Mapped[str | None] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SalesforceObject(UUIDPk, Base):
    __tablename__ = "salesforce_objects"
    __table_args__ = (UniqueConstraint("connection_id", "object_api_name", name="uq_sf_obj_conn_name"),)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("salesforce_connections.id", ondelete="CASCADE"), index=True)
    object_api_name: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    label_plural: Mapped[str | None] = mapped_column(String(255))
    key_prefix: Mapped[str | None] = mapped_column(String(5))
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    is_queryable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_version: Mapped[str | None] = mapped_column(String(32))
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    fields: Mapped[list["SalesforceField"]] = relationship(back_populates="object", cascade="all, delete-orphan")


class SalesforceField(UUIDPk, Base):
    __tablename__ = "salesforce_fields"
    __table_args__ = (UniqueConstraint("object_id", "field_api_name", name="uq_sf_field_obj_name"),)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    object_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("salesforce_objects.id", ondelete="CASCADE"), index=True)
    field_api_name: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reference_to: Mapped[list] = mapped_column(JSONB, default=list)
    relationship_name: Mapped[str | None] = mapped_column(String(255))
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    is_queryable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_filterable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_groupable: Mapped[bool] = mapped_column(Boolean, default=False)
    is_sortable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_aggregatable: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    object: Mapped[SalesforceObject] = relationship(back_populates="fields")


class SalesforceRelationship(UUIDPk, Base):
    __tablename__ = "salesforce_relationships"
    __table_args__ = (
        UniqueConstraint("object_id", "relationship_name", "direction", name="uq_sf_rel_obj_name_dir"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    object_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("salesforce_objects.id", ondelete="CASCADE"), index=True)
    related_object_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("salesforce_objects.id", ondelete="SET NULL"))
    related_object_api_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relationship_name: Mapped[str] = mapped_column(String(255), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # parent|child
    relationship_type: Mapped[str] = mapped_column(String(20), nullable=False)  # lookup|master_detail
    field_api_name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class SavedQuery(UUIDPk, Timestamps, Base):
    __tablename__ = "saved_queries"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("salesforce_connections.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    question_examples: Mapped[list] = mapped_column(JSONB, default=list)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    parameters_schema: Mapped[dict] = mapped_column(JSONB, default=dict)
    plan_json: Mapped[dict | None] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    visibility: Mapped[str] = mapped_column(String(10), default="private", nullable=False)  # private|tenant
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class QueryExecution(UUIDPk, Timestamps, Base):
    __tablename__ = "query_executions"
    __table_args__ = (Index("ix_query_exec_tenant_created", "tenant_id", "created_at"),)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    connection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("salesforce_connections.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    saved_query_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("saved_queries.id", ondelete="SET NULL"))
    question: Mapped[str | None] = mapped_column(Text)
    plan_json: Mapped[dict | None] = mapped_column(JSONB)
    generated_soql: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="ai")  
    interface: Mapped[str] = mapped_column(String(10), default="web")  
    status: Mapped[str] = mapped_column(String(20), default="planned")
    validation_json: Mapped[dict | None] = mapped_column(JSONB)
    row_count: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(String(100))
    token_usage: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(UUIDPk, Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_tenant_created", "tenant_id", "created_at"),)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50))
    resource_id: Mapped[str | None] = mapped_column(String(100))
    result: Mapped[str] = mapped_column(String(20), default="success")
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class AIUsage(UUIDPk, Base):
    __tablename__ = "ai_usage"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    execution_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("query_executions.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(30))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SyncRun(UUIDPk, Base):
    __tablename__ = "sync_runs"
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("salesforce_connections.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(20), default="full")
    status: Mapped[str] = mapped_column(String(20), default="queued")  
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    objects_seen: Mapped[int] = mapped_column(Integer, default=0)
    fields_seen: Mapped[int] = mapped_column(Integer, default=0)
    relationships_seen: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    error_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
