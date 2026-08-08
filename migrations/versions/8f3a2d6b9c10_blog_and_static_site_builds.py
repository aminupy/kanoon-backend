"""add structured blog publishing and durable static-site builds

Revision ID: 8f3a2d6b9c10
Revises: bfd7cd1209eb
Create Date: 2026-08-07 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8f3a2d6b9c10"
down_revision: str | Sequence[str] | None = "bfd7cd1209eb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tenant_rls(table_name: str) -> None:
    predicate = "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f'CREATE POLICY tenant_isolation ON "{table_name}" '
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
    )


def upgrade() -> None:
    empty_document = sa.text('\'{"type": "doc", "content": []}\'::jsonb')
    op.add_column(
        "posts",
        sa.Column(
            "content_document",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=empty_document,
            nullable=False,
        ),
    )
    op.add_column("posts", sa.Column("rendered_html", sa.Text(), nullable=True))
    op.add_column("posts", sa.Column("og_image_id", sa.Uuid(), nullable=True))
    op.add_column("posts", sa.Column("seo_title", sa.String(length=300), nullable=True))
    op.add_column("posts", sa.Column("seo_description", sa.String(length=500), nullable=True))
    op.add_column("posts", sa.Column("created_by", sa.Uuid(), nullable=True))
    op.add_column("posts", sa.Column("updated_by", sa.Uuid(), nullable=True))
    op.execute(
        """
        UPDATE posts
        SET content_document = jsonb_build_object(
            'type', 'doc',
            'content', CASE WHEN body = '' THEN '[]'::jsonb ELSE jsonb_build_array(
                jsonb_build_object(
                    'type', 'paragraph',
                    'content', jsonb_build_array(jsonb_build_object('type', 'text', 'text', body))
                )
            ) END
        ),
        rendered_html = CASE WHEN body = '' THEN '' ELSE
            '<p>' || replace(replace(replace(body, '&', '&amp;'), '<', '&lt;'), '>', '&gt;') || '</p>'
        END
        """
    )
    op.create_foreign_key(
        op.f("fk_posts_created_by_users"), "posts", "users", ["created_by"], ["id"]
    )
    op.create_foreign_key(
        op.f("fk_posts_updated_by_users"), "posts", "users", ["updated_by"], ["id"]
    )
    op.create_foreign_key(
        op.f("fk_posts_tenant_id_og_image_id_media_assets"),
        "posts",
        "media_assets",
        ["tenant_id", "og_image_id"],
        ["tenant_id", "id"],
    )

    op.create_table(
        "tenant_site_build_configs",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("canonical_domain", sa.String(length=253), nullable=False),
        sa.Column("build_target_key", sa.String(length=200), nullable=False),
        sa.Column("deployment_target_key", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_tenant_site_build_configs_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", name=op.f("pk_tenant_site_build_configs")),
    )
    op.create_table(
        "tenant_site_states",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("content_revision", sa.BigInteger(), nullable=False),
        sa.Column("last_successful_build_revision", sa.BigInteger(), nullable=True),
        sa.Column("last_build_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "content_revision >= 0",
            name=op.f("ck_tenant_site_states_content_revision_nonnegative"),
        ),
        sa.CheckConstraint(
            "last_successful_build_revision IS NULL OR last_successful_build_revision >= 0",
            name=op.f("ck_tenant_site_states_deployed_revision_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_tenant_site_states_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", name=op.f("pk_tenant_site_states")),
    )
    op.create_table(
        "post_media_references",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("media_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "media_id"],
            ["media_assets.tenant_id", "media_assets.id"],
            name=op.f("fk_post_media_references_tenant_id_media_id_media_assets"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "post_id"],
            ["posts.tenant_id", "posts.id"],
            name=op.f("fk_post_media_references_tenant_id_post_id_posts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_post_media_references_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_post_media_references")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_post_media_references_tenant_id_id")),
        sa.UniqueConstraint(
            "tenant_id",
            "post_id",
            "media_id",
            name=op.f("uq_post_media_references_tenant_id_post_id_media_id"),
        ),
    )
    op.create_index(
        "ix_post_media_references_tenant_media",
        "post_media_references",
        ["tenant_id", "media_id"],
    )
    op.create_index(
        "ix_post_media_references_tenant_post",
        "post_media_references",
        ["tenant_id", "post_id"],
    )
    op.create_table(
        "site_build_requests",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("target_revision", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_revision", sa.BigInteger(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_site_build_requests_attempt_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "target_revision >= 0",
            name=op.f("ck_site_build_requests_target_revision_nonnegative"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCESSFUL', 'FAILED', 'SUPERSEDED')",
            name=op.f("ck_site_build_requests_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_site_build_requests_created_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_site_build_requests_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_site_build_requests")),
        sa.UniqueConstraint("tenant_id", "id", name=op.f("uq_site_build_requests_tenant_id_id")),
    )
    op.create_index(
        "ix_site_build_requests_poll",
        "site_build_requests",
        ["status", "next_attempt_at", "requested_at"],
    )
    op.create_index(
        "ix_site_build_requests_tenant_status_requested",
        "site_build_requests",
        ["tenant_id", "status", "requested_at"],
    )
    op.create_index(
        "uq_site_build_requests_one_pending_per_tenant",
        "site_build_requests",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "uq_site_build_requests_one_running_per_tenant",
        "site_build_requests",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("status = 'RUNNING'"),
    )

    for table_name in (
        "post_media_references",
        "site_build_requests",
        "tenant_site_build_configs",
        "tenant_site_states",
    ):
        _tenant_rls(table_name)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON "
        "post_media_references, site_build_requests, tenant_site_build_configs, "
        "tenant_site_states TO kanoon_app"
    )


def downgrade() -> None:
    op.drop_index("uq_site_build_requests_one_running_per_tenant", table_name="site_build_requests")
    op.drop_index("uq_site_build_requests_one_pending_per_tenant", table_name="site_build_requests")
    op.drop_index(
        "ix_site_build_requests_tenant_status_requested", table_name="site_build_requests"
    )
    op.drop_index("ix_site_build_requests_poll", table_name="site_build_requests")
    op.drop_table("site_build_requests")
    op.drop_index("ix_post_media_references_tenant_post", table_name="post_media_references")
    op.drop_index("ix_post_media_references_tenant_media", table_name="post_media_references")
    op.drop_table("post_media_references")
    op.drop_table("tenant_site_states")
    op.drop_table("tenant_site_build_configs")
    op.drop_constraint(
        op.f("fk_posts_tenant_id_og_image_id_media_assets"), "posts", type_="foreignkey"
    )
    op.drop_constraint(op.f("fk_posts_updated_by_users"), "posts", type_="foreignkey")
    op.drop_constraint(op.f("fk_posts_created_by_users"), "posts", type_="foreignkey")
    op.drop_column("posts", "updated_by")
    op.drop_column("posts", "created_by")
    op.drop_column("posts", "seo_description")
    op.drop_column("posts", "seo_title")
    op.drop_column("posts", "og_image_id")
    op.drop_column("posts", "rendered_html")
    op.drop_column("posts", "content_document")
