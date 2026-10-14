"""Saved queries, query executions, AI usage (Steps 11-13).

Revision ID: 0003
Revises: 0002
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('saved_queries',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('connection_id', sa.UUID(), nullable=False),
    sa.Column('owner_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('question_examples', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('template', sa.Text(), nullable=False),
    sa.Column('parameters_schema', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('plan_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('visibility', sa.String(length=10), nullable=False),
    sa.Column('use_count', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['salesforce_connections.id'], name=op.f('fk_saved_queries_connection_id_salesforce_connections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_saved_queries_owner_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_saved_queries_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_saved_queries'))
    )
    op.create_index(op.f('ix_saved_queries_connection_id'), 'saved_queries', ['connection_id'], unique=False)
    op.create_index(op.f('ix_saved_queries_tenant_id'), 'saved_queries', ['tenant_id'], unique=False)
    op.create_table('query_executions',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('connection_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('saved_query_id', sa.UUID(), nullable=True),
    sa.Column('question', sa.Text(), nullable=True),
    sa.Column('plan_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('generated_soql', sa.Text(), nullable=True),
    sa.Column('explanation', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('interface', sa.String(length=10), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('validation_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('row_count', sa.Integer(), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('model', sa.String(length=100), nullable=True),
    sa.Column('token_usage', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('correlation_id', sa.String(length=64), nullable=True),
    sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['salesforce_connections.id'], name=op.f('fk_query_executions_connection_id_salesforce_connections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['saved_query_id'], ['saved_queries.id'], name=op.f('fk_query_executions_saved_query_id_saved_queries'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_query_executions_tenant_id_tenants'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_query_executions_user_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_query_executions'))
    )
    op.create_index('ix_query_exec_tenant_created', 'query_executions', ['tenant_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_query_executions_correlation_id'), 'query_executions', ['correlation_id'], unique=False)
    op.create_table('ai_usage',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('execution_id', sa.UUID(), nullable=True),
    sa.Column('provider', sa.String(length=50), nullable=False),
    sa.Column('model', sa.String(length=100), nullable=False),
    sa.Column('prompt_version', sa.String(length=30), nullable=True),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('estimated_cost', sa.Numeric(precision=12, scale=6), nullable=False),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['execution_id'], ['query_executions.id'], name=op.f('fk_ai_usage_execution_id_query_executions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name=op.f('fk_ai_usage_tenant_id_tenants'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_usage'))
    )
    op.create_index(op.f('ix_ai_usage_tenant_id'), 'ai_usage', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ai_usage_tenant_id'), table_name='ai_usage')
    op.drop_table('ai_usage')
    op.drop_index('ix_query_exec_tenant_created', table_name='query_executions')
    op.drop_index(op.f('ix_query_executions_correlation_id'), table_name='query_executions')
    op.drop_table('query_executions')
    op.drop_index(op.f('ix_saved_queries_connection_id'), table_name='saved_queries')
    op.drop_index(op.f('ix_saved_queries_tenant_id'), table_name='saved_queries')
    op.drop_table('saved_queries')
