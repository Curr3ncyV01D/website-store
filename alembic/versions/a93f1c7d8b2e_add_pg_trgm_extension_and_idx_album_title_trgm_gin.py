"""pg_trgm extension + gin index idx_album_title_trgm on albums.clean_title

Revision ID: a93f1c7d8b2e
Revises: be3675542bee
Create Date: 2026-09-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a93f1c7d8b2e"
down_revision: Union[str, None] = "be3675542bee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "idx_album_title_trgm",
        "albums",
        ["clean_title"],
        postgresql_using="gin",
        postgresql_ops={"clean_title": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("idx_album_title_trgm", table_name="albums")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
