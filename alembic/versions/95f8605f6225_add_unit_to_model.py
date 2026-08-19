"""add unit to model

Revision ID: 95f8605f6225
Revises: b850bc69c669
Create Date: 2026-08-19 16:35:51.841724

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '95f8605f6225'
down_revision: Union[str, Sequence[str], None] = 'b850bc69c669'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Produit : unité par défaut (nullable, pas de souci)
    op.add_column("sales_products", sa.Column("default_unit", sa.String(20), nullable=True))

    # --- sales_order_items : ajout sûr en 3 temps ---
    # 1) colonne nullable
    op.add_column("sales_order_items", sa.Column("unit", sa.String(20), nullable=True))
    # 2) remplir les lignes existantes
    op.execute("UPDATE sales_order_items SET unit = 'pièce' WHERE unit IS NULL")
    # 3) poser la contrainte NOT NULL maintenant que tout est rempli
    op.alter_column("sales_order_items", "unit", nullable=False)

    # --- sales_proforma_items : idem ---
    op.add_column("sales_proforma_items", sa.Column("unit", sa.String(20), nullable=True))
    op.execute("UPDATE sales_proforma_items SET unit = 'pièce' WHERE unit IS NULL")
    op.alter_column("sales_proforma_items", "unit", nullable=False)


def downgrade() -> None:
    op.drop_column("sales_proforma_items", "unit")
    op.drop_column("sales_order_items", "unit")
    op.drop_column("sales_products", "default_unit")