"""Identity, tenancy, credential store, Salesforce connections, audit trail (Steps 5-6).

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
    )
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "audit_events",
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=True),
        sa.Column("resource_id", sa.String(length=100), nullable=True),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_audit_events_tenant_id_tenants"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_audit_events_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(op.f("ix_audit_events_correlation_id"), "audit_events", ["correlation_id"], unique=False)
    op.create_index("ix_audit_tenant_created", "audit_events", ["tenant_id", "created_at"], unique=False)
    op.create_table(
        "credential_secrets",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_credential_secrets_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credential_secrets")),
    )
    op.create_index(op.f("ix_credential_secrets_tenant_id"), "credential_secrets", ["tenant_id"], unique=False)
    op.create_table(
        "tenant_users",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_tenant_users_tenant_id_tenants"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_tenant_users_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id", "user_id", name=op.f("pk_tenant_users")),
    )
    op.create_table(
        "salesforce_connections",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("org_id", sa.String(length=18), nullable=False),
        sa.Column("org_name", sa.String(length=255), nullable=True),
        sa.Column("instance_url", sa.String(length=500), nullable=False),
        sa.Column("sf_username", sa.String(length=320), nullable=True),
        sa.Column("sf_user_id", sa.String(length=18), nullable=True),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("api_version", sa.String(length=10), nullable=False),
        sa.Column("auth_ref", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("catalog_version", sa.String(length=32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["auth_ref"], ["credential_secrets.id"], name=op.f("fk_salesforce_connections_auth_ref_credential_secrets"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_salesforce_connections_created_by_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_salesforce_connections_tenant_id_tenants"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_salesforce_connections")),
        sa.UniqueConstraint("tenant_id", "org_id", name="uq_sf_conn_tenant_org"),
    )
    op.create_index(op.f("ix_salesforce_connections_tenant_id"), "salesforce_connections", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_salesforce_connections_tenant_id"), table_name="salesforce_connections")
    op.drop_table("salesforce_connections")
    op.drop_table("tenant_users")
    op.drop_index(op.f("ix_credential_secrets_tenant_id"), table_name="credential_secrets")
    op.drop_table("credential_secrets")
    op.drop_index(op.f("ix_audit_events_correlation_id"), table_name="audit_events")
    op.drop_index("ix_audit_tenant_created", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("users")
    op.drop_table("tenants")
