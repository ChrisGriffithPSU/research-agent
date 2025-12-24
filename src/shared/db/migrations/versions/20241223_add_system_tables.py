"""Add system tables for state management, fetcher tracking, and learning.

Revision ID: 002
Revises: 001
Create Date: 2024-12-23

Adds tables:
- system_state: Key-value store for system configuration
- fetcher_state: Track fetcher health and status
- search_queries: History of LLM-generated queries
- model_metadata: Learning model versioning
- preference_weights: Store learned preference scores
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create system_state table
    op.create_table(
        'system_state',
        sa.Column('key', sa.String(length=255), nullable=False),
        sa.Column('value', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('key')
    )

    # Create fetcher_state table
    op.create_table(
        'fetcher_state',
        sa.Column('fetcher_name', sa.String(length=50), nullable=False),
        sa.Column('last_fetch_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_count', sa.Integer(), nullable=False),
        sa.Column('config', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('fetcher_name')
    )
    op.create_index(op.f('ix_fetcher_state_status'), 'fetcher_state', ['status'], unique=False)

    # Create search_queries table
    op.create_table(
        'search_queries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('query_text', sa.Text(), nullable=False),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('results_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_search_queries_source'), 'search_queries', ['source'], unique=False)

    # Create model_metadata table
    op.create_table(
        'model_metadata',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('version', sa.String(length=50), nullable=False),
        sa.Column('trained_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('training_samples', sa.Integer(), nullable=False),
        sa.Column('performance_metrics', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('file_path', sa.String(length=512), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_model_metadata_version'), 'model_metadata', ['version'], unique=False)

    # Create preference_weights table
    op.create_table(
        'preference_weights',
        sa.Column('dimension', sa.String(length=100), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('dimension')
    )


def downgrade() -> None:
    # Drop in reverse order of creation
    op.drop_index(op.f('ix_preference_weights_dimension'), table_name='preference_weights')
    op.drop_table('preference_weights')

    op.drop_index(op.f('ix_model_metadata_version'), table_name='model_metadata')
    op.drop_table('model_metadata')

    op.drop_index(op.f('ix_search_queries_source'), table_name='search_queries')
    op.drop_table('search_queries')

    op.drop_index(op.f('ix_fetcher_state_status'), table_name='fetcher_state')
    op.drop_table('fetcher_state')

    op.drop_table('system_state')

