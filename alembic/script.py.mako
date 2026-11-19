"""${message}

Revision ID: ${rev}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = ${rev!r}
down_revision: Union[str, None] = ${down_revision!r}
branch_labels: Union[str, Sequence[str], None] = ${branch_labels!r}
depends_on: Union[str, Sequence[str], None] = ${depends_on!r}


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
