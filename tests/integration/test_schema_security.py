from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration

TENANT_TABLES = {
    "audit_events",
    "banners",
    "contact_requests",
    "exam_offerings",
    "exam_pricing_plans",
    "gallery_albums",
    "gallery_items",
    "honor_categories",
    "honors",
    "media_assets",
    "otp_challenges",
    "payment_transactions",
    "post_media_references",
    "posts",
    "pricing_plans",
    "registration_contacts",
    "registration_form_definitions",
    "registrations",
    "sample_exams",
    "site_build_requests",
    "staff_members",
    "tenant_addresses",
    "tenant_features",
    "tenant_memberships",
    "tenant_phones",
    "tenant_profiles",
    "tenant_social_links",
    "tenant_site_build_configs",
    "tenant_site_states",
}


async def test_every_tenant_table_has_forced_rls_and_policy(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                           pg_get_userbyid(c.relowner) AS owner,
                           count(p.polname) AS policy_count
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    LEFT JOIN pg_policy p ON p.polrelid = c.oid
                    WHERE n.nspname = 'public' AND c.relkind = 'r'
                    GROUP BY c.oid
                    """
                )
            )
        ).mappings()
        tables = {str(row["relname"]): row for row in rows}
        tenant_columns = set(
            (
                await connection.scalars(
                    text(
                        """
                        SELECT table_name FROM information_schema.columns
                        WHERE table_schema = 'public' AND column_name = 'tenant_id'
                        """
                    )
                )
            ).all()
        )
        role = (
            await connection.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'kanoon_app'")
            )
        ).one()

    assert tenant_columns >= TENANT_TABLES
    assert tenant_columns - TENANT_TABLES == {"tenant_domains", "refresh_tokens"}
    assert role == (False, False)
    for table_name in TENANT_TABLES:
        table = tables[table_name]
        assert table["relrowsecurity"] is True, table_name
        assert table["relforcerowsecurity"] is True, table_name
        assert table["policy_count"] >= 1, table_name
        assert table["owner"] != "kanoon_app", table_name


async def test_foreign_keys_between_tenant_tables_are_tenant_aware(
    owner_engine: AsyncEngine,
) -> None:
    def foreign_keys(sync_connection: Any) -> dict[str, list[dict[str, Any]]]:
        inspector = inspect(sync_connection)
        return {table: inspector.get_foreign_keys(table) for table in TENANT_TABLES}

    async with owner_engine.connect() as connection:
        keys = await connection.run_sync(foreign_keys)

    for child_table, foreign_key_list in keys.items():
        for foreign_key in foreign_key_list:
            parent = foreign_key["referred_table"]
            if parent in TENANT_TABLES:
                assert "tenant_id" in foreign_key["constrained_columns"], (
                    child_table,
                    parent,
                    foreign_key,
                )
                assert "tenant_id" in foreign_key["referred_columns"], (
                    child_table,
                    parent,
                    foreign_key,
                )
