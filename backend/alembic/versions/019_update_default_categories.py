"""update default categories: rename, add pets/investments/travel, remove donations/personal_care

Revision ID: 019
Revises: 018
Create Date: 2026-03-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Simple renames (no conflict risk) ─────────────────────────────────
    simple_renames = [
        ("Alimentação",     "Restaurantes & Delivery", "utensils-crossed"),
        ("Saúde",           "Saúde & Bem-estar",        "heart-pulse"),
        ("Impostos & Taxas","Impostos & Tributos",      "landmark"),
        ("Food & Dining",   "Restaurants & Delivery",   "utensils-crossed"),
        ("Health",          "Health & Wellness",        "heart-pulse"),
        ("Taxes & Fees",    "Taxes & Duties",           "landmark"),
    ]
    for old_name, new_name, new_icon in simple_renames:
        conn.execute(sa.text("""
            UPDATE categories SET name = :new_name, icon = :new_icon
            WHERE is_system = TRUE AND name = :old_name
        """), {"old_name": old_name, "new_name": new_name, "new_icon": new_icon})

    # ── 2. Merge "Cuidados Pessoais" / "Personal Care" into health category ──
    # Move transactions, then delete the old row.
    for merge_from, merge_into in [
        ("Cuidados Pessoais", "Saúde & Bem-estar"),
        ("Personal Care",     "Health & Wellness"),
    ]:
        conn.execute(sa.text("""
            WITH mapping AS (
                SELECT c_from.id AS from_id, c_into.id AS into_id
                FROM categories c_from
                JOIN categories c_into
                  ON c_into.user_id = c_from.user_id
                 AND c_into.name = :merge_into
                 AND c_into.is_system = TRUE
                WHERE c_from.is_system = TRUE AND c_from.name = :merge_from
            )
            UPDATE transactions t
            SET category_id = m.into_id
            FROM mapping m WHERE t.category_id = m.from_id
        """), {"merge_from": merge_from, "merge_into": merge_into})

        conn.execute(sa.text("""
            DELETE FROM categories WHERE is_system = TRUE AND name = :merge_from
        """), {"merge_from": merge_from})

    # ── 3. Migrate "Doações" transactions to "Outros" then delete ────────────
    for donations_name in ("Doações", "Donations"):
        conn.execute(sa.text("""
            WITH donation_cats AS (
                SELECT c_don.id AS don_id, c_other.id AS other_id
                FROM categories c_don
                JOIN categories c_other
                  ON c_other.user_id = c_don.user_id
                 AND c_other.name IN ('Outros', 'Other')
                 AND c_other.is_system = TRUE
                WHERE c_don.is_system = TRUE AND c_don.name = :donations_name
            )
            UPDATE transactions t
            SET category_id = d.other_id
            FROM donation_cats d
            WHERE t.category_id = d.don_id
        """), {"donations_name": donations_name})

        conn.execute(sa.text("""
            DELETE FROM categories
            WHERE is_system = TRUE AND name = :donations_name
        """), {"donations_name": donations_name})

    # ── 4. Add new system categories for each existing user ──────────────────
    new_categories = [
        # (name_pt, name_en, icon, color, group_name_pt, group_name_en)
        ("Pets",         "Pets",         "paw-print",   "#A78BFA", "Estilo de Vida", "Lifestyle"),
        ("Investimentos","Investments",  "trending-up", "#059669", "Renda",          "Income"),
        ("Viagens",      "Travel",       "plane",       "#0EA5E9", "Estilo de Vida", "Lifestyle"),
    ]

    # Get all users that have system categories
    users = conn.execute(sa.text("""
        SELECT DISTINCT user_id FROM categories WHERE is_system = TRUE
    """)).fetchall()

    for (user_id,) in users:
        # Detect language by checking which name exists
        is_pt = conn.execute(sa.text("""
            SELECT 1 FROM categories
            WHERE user_id = :uid AND name = 'Moradia' AND is_system = TRUE
        """), {"uid": user_id}).fetchone() is not None

        for name_pt, name_en, icon, color, group_pt, group_en in new_categories:
            name = name_pt if is_pt else name_en
            group_name = group_pt if is_pt else group_en

            # Skip if already exists
            exists = conn.execute(sa.text("""
                SELECT 1 FROM categories WHERE user_id = :uid AND name = :name
            """), {"uid": user_id, "name": name}).fetchone()
            if exists:
                continue

            # Find group
            group = conn.execute(sa.text("""
                SELECT id FROM category_groups WHERE user_id = :uid AND name = :gname
            """), {"uid": user_id, "gname": group_name}).fetchone()
            group_id = group[0] if group else None

            conn.execute(sa.text("""
                INSERT INTO categories (id, user_id, name, icon, color, is_system, group_id)
                VALUES (gen_random_uuid(), :uid, :name, :icon, :color, TRUE, :group_id)
            """), {"uid": user_id, "name": name, "icon": icon, "color": color, "group_id": group_id})


def downgrade() -> None:
    conn = op.get_bind()

    # Remove added categories
    for name in ("Pets", "Investimentos", "Investments", "Viagens", "Travel"):
        conn.execute(sa.text("""
            DELETE FROM categories WHERE is_system = TRUE AND name = :name
        """), {"name": name})

    # Rename back
    renames_back = [
        ("Restaurantes & Delivery", "Alimentação",     "utensils-crossed"),
        ("Saúde & Bem-estar",       "Saúde",           "pill"),
        ("Impostos & Tributos",     "Impostos & Taxas","landmark"),
        ("Restaurants & Delivery",  "Food & Dining",   "utensils-crossed"),
        ("Health & Wellness",       "Health",          "pill"),
        ("Taxes & Duties",          "Taxes & Fees",    "landmark"),
    ]
    for old_name, new_name, new_icon in renames_back:
        conn.execute(sa.text("""
            UPDATE categories SET name = :new_name, icon = :new_icon
            WHERE is_system = TRUE AND name = :old_name
        """), {"old_name": old_name, "new_name": new_name, "new_icon": new_icon})
