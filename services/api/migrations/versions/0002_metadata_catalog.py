"""Metadata catalog + sync runs (Step 9).

Revision ID: 0002
Revises: 0001
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('salesforce_objects',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('connection_id', sa.UUID(), nullable=False),
    sa.Column('object_api_name', sa.String(length=255), nullable=False),
    sa.Column('label', sa.String(length=255), nullable=False),
    sa.Column('label_plural', sa.String(length=255), nullable=True),
    sa.Column('key_prefix', sa.String(length=5), nullable=True),
    sa.Column('is_custom', sa.Boolean(), nullable=False),
    sa.Column('is_queryable', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('metadata_version', sa.String(length=32), nullable=True),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['salesforce_connections.id'], name=op.f('fk_salesforce_objects_connection_id_salesforce_connections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_salesforce_objects_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_salesforce_objects')),
    sa.UniqueConstraint('connection_id', 'object_api_name', name='uq_sf_obj_conn_name')
    )
    op.create_index(op.f('ix_salesforce_objects_connection_id'), 'salesforce_objects', ['connection_id'], unique=False)
    op.create_index(op.f('ix_salesforce_objects_tenant_id'), 'salesforce_objects', ['tenant_id'], unique=False)
    op.create_table('sync_runs',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('connection_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('objects_seen', sa.Integer(), nullable=False),
    sa.Column('fields_seen', sa.Integer(), nullable=False),
    sa.Column('relationships_seen', sa.Integer(), nullable=False),
    sa.Column('error_count', sa.Integer(), nullable=False),
    sa.Column('error_detail', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['salesforce_connections.id'], name=op.f('fk_sync_runs_connection_id_salesforce_connections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_sync_runs_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sync_runs'))
    )
    op.create_index(op.f('ix_sync_runs_connection_id'), 'sync_runs', ['connection_id'], unique=False)
    op.create_index(op.f('ix_sync_runs_tenant_id'), 'sync_runs', ['tenant_id'], unique=False)
    op.create_table('salesforce_fields',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('object_id', sa.UUID(), nullable=False),
    sa.Column('field_api_name', sa.String(length=255), nullable=False),
    sa.Column('label', sa.String(length=255), nullable=False),
    sa.Column('data_type', sa.String(length=40), nullable=False),
    sa.Column('reference_to', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('relationship_name', sa.String(length=255), nullable=True),
    sa.Column('is_custom', sa.Boolean(), nullable=False),
    sa.Column('is_queryable', sa.Boolean(), nullable=False),
    sa.Column('is_filterable', sa.Boolean(), nullable=False),
    sa.Column('is_groupable', sa.Boolean(), nullable=False),
    sa.Column('is_sortable', sa.Boolean(), nullable=False),
    sa.Column('is_aggregatable', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['object_id'], ['salesforce_objects.id'], name=op.f('fk_salesforce_fields_object_id_salesforce_objects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_salesforce_fields_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_salesforce_fields')),
    sa.UniqueConstraint('object_id', 'field_api_name', name='uq_sf_field_obj_name')
    )
    op.create_index(op.f('ix_salesforce_fields_object_id'), 'salesforce_fields', ['object_id'], unique=False)
    op.create_index(op.f('ix_salesforce_fields_tenant_id'), 'salesforce_fields', ['tenant_id'], unique=False)
    op.create_table('salesforce_relationships',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('object_id', sa.UUID(), nullable=False),
    sa.Column('related_object_id', sa.UUID(), nullable=True),
    sa.Column('related_object_api_name', sa.String(length=255), nullable=False),
    sa.Column('relationship_name', sa.String(length=255), nullable=False),
    sa.Column('direction', sa.String(length=10), nullable=False),
    sa.Column('relationship_type', sa.String(length=20), nullable=False),
    sa.Column('field_api_name', sa.String(length=255), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['object_id'], ['salesforce_objects.id'], name=op.f('fk_salesforce_relationships_object_id_salesforce_objects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['related_object_id'], ['salesforce_objects.id'], name=op.f('fk_salesforce_relationships_related_object_id_salesforce_objects'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_salesforce_relationships_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_salesforce_relationships')),
    sa.UniqueConstraint('object_id', 'relationship_name', 'direction', name='uq_sf_rel_obj_name_dir')
    )
    op.create_index(op.f('ix_salesforce_relationships_object_id'), 'salesforce_relationships', ['object_id'], unique=False)
    op.create_index(op.f('ix_salesforce_relationships_tenant_id'), 'salesforce_relationships', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_salesforce_relationships_object_id'), table_name='salesforce_relationships')
    op.drop_index(op.f('ix_salesforce_relationships_tenant_id'), table_name='salesforce_relationships')
    op.drop_table('salesforce_relationships')
    op.drop_index(op.f('ix_salesforce_fields_object_id'), table_name='salesforce_fields')
    op.drop_index(op.f('ix_salesforce_fields_tenant_id'), table_name='salesforce_fields')
    op.drop_table('salesforce_fields')
    op.drop_index(op.f('ix_sync_runs_connection_id'), table_name='sync_runs')
    op.drop_index(op.f('ix_sync_runs_tenant_id'), table_name='sync_runs')
    op.drop_table('sync_runs')
    op.drop_index(op.f('ix_salesforce_objects_connection_id'), table_name='salesforce_objects')
    op.drop_index(op.f('ix_salesforce_objects_tenant_id'), table_name='salesforce_objects')
    op.drop_table('salesforce_objects')
