"""Initial schema with pgvector support

Revision ID: 001
Revises:
Create Date: 2024-12-22

Creates all core tables:
- user_profiles: User preferences and settings
- sources: Raw content from fetchers with embeddings
- digests: Daily curated digests
- digest_items: Individual items in digests
- feedback: User feedback for learning system
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create user_profiles table
    op.create_table(
        'user_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('preferences', sa.JSON(), nullable=False),
        sa.Column('learning_config', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_user_profiles_email'), 'user_profiles', ['email'], unique=True)

    # Create sources table
    op.create_table(
        'sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_type', sa.String(length=20), nullable=False),
        sa.Column('url', sa.String(length=2048), nullable=False),
        sa.Column('title', sa.String(length=512), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('extracted_data', sa.JSON(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url')
    )
    op.create_index(op.f('ix_sources_source_type'), 'sources', ['source_type'], unique=False)
    op.create_index(op.f('ix_sources_status'), 'sources', ['status'], unique=False)
    op.create_index(op.f('ix_sources_url'), 'sources', ['url'], unique=True)

    # Create vector similarity index for embeddings (HNSW for better performance)
    op.execute('CREATE INDEX ix_sources_embedding_hnsw ON sources USING hnsw (embedding vector_cosine_ops)')

    # Create digests table
    op.create_table(
        'digests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('digest_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user_profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_digests_user_id'), 'digests', ['user_id'], unique=False)
    op.create_index(op.f('ix_digests_digest_date'), 'digests', ['digest_date'], unique=False)
    op.create_index(op.f('ix_digests_status'), 'digests', ['status'], unique=False)

    # Create digest_items table
    op.create_table(
        'digest_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('digest_id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=512), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('reasoning', sa.Text(), nullable=False),
        sa.Column('tags', sa.ARRAY(sa.String(length=100)), nullable=False),
        sa.Column('relevance_score', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['digest_id'], ['digests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_digest_items_digest_id'), 'digest_items', ['digest_id'], unique=False)
    op.create_index(op.f('ix_digest_items_source_id'), 'digest_items', ['source_id'], unique=False)

    # Create feedback table
    op.create_table(
        'feedback',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('digest_item_id', sa.Integer(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('time_spent', sa.Float(), nullable=True),
        sa.Column('clicked_through', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['digest_item_id'], ['digest_items.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_feedback_digest_item_id'), 'feedback', ['digest_item_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_feedback_digest_item_id'), table_name='feedback')
    op.drop_table('feedback')

    op.drop_index(op.f('ix_digest_items_source_id'), table_name='digest_items')
    op.drop_index(op.f('ix_digest_items_digest_id'), table_name='digest_items')
    op.drop_table('digest_items')

    op.drop_index(op.f('ix_digests_status'), table_name='digests')
    op.drop_index(op.f('ix_digests_digest_date'), table_name='digests')
    op.drop_index(op.f('ix_digests_user_id'), table_name='digests')
    op.drop_table('digests')

    op.execute('DROP INDEX IF EXISTS ix_sources_embedding_hnsw')
    op.drop_index(op.f('ix_sources_url'), table_name='sources')
    op.drop_index(op.f('ix_sources_status'), table_name='sources')
    op.drop_index(op.f('ix_sources_source_type'), table_name='sources')
    op.drop_table('sources')

    op.drop_index(op.f('ix_user_profiles_email'), table_name='user_profiles')
    op.drop_table('user_profiles')
