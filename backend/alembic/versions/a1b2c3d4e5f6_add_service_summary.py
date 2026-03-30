"""add summary column to services

Revision ID: a1b2c3d4e5f6
Revises: 51535ee764d6
Create Date: 2026-03-28

"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "51535ee764d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("services", sa.Column("summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("services", "summary")
