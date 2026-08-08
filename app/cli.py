from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from datetime import UTC, datetime

import uvicorn
from sqlalchemy import select, text

from app.auth.models import TenantMembership, User
from app.auth.security import hash_password
from app.core.config import get_settings
from app.core.database import Database
from app.site_builds.executor import WebhookSiteBuildExecutor
from app.site_builds.worker import SiteBuildWorker
from app.tenancy.context import normalize_hostname
from app.tenancy.features import FEATURE_KEYS
from app.tenancy.models import Tenant, TenantDomain, TenantFeature


async def bootstrap(args: argparse.Namespace) -> None:
    settings = get_settings()
    password = os.getenv("KANOON_BOOTSTRAP_PASSWORD")
    if not password:
        if not sys.stdin.isatty():
            raise RuntimeError("set KANOON_BOOTSTRAP_PASSWORD in non-interactive environments")
        password = getpass.getpass("Platform administrator password: ")
    if len(password) < 12:
        raise RuntimeError("bootstrap password must contain at least 12 characters")

    database = Database(settings)
    try:
        async with database.global_session() as session:
            email = args.email.casefold()
            user = await session.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(
                    email=email,
                    password_hash=hash_password(password),
                    is_active=True,
                    is_platform_admin=True,
                )
                session.add(user)
                await session.flush()
            else:
                user.is_platform_admin = True
                user.is_active = True

            if args.tenant_slug:
                tenant = await session.scalar(select(Tenant).where(Tenant.slug == args.tenant_slug))
                if tenant is None:
                    tenant = Tenant(
                        name=args.tenant_name,
                        slug=args.tenant_slug,
                        status="ACTIVE",
                        default_locale="fa-IR",
                        timezone="Asia/Tehran",
                        default_currency="IRR",
                    )
                    session.add(tenant)
                    await session.flush()
                    session.add(
                        TenantDomain(
                            tenant_id=tenant.id,
                            hostname=normalize_hostname(args.tenant_domain),
                            is_primary=True,
                            is_active=True,
                            created_at=datetime.now(UTC),
                        )
                    )
                    await session.execute(
                        text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
                        {"tenant_id": str(tenant.id)},
                    )
                    session.add_all(
                        TenantFeature(
                            tenant_id=tenant.id,
                            feature_key=feature,
                            enabled=True,
                            configuration={},
                        )
                        for feature in FEATURE_KEYS
                    )
                    session.add(
                        TenantMembership(
                            tenant_id=tenant.id,
                            user_id=user.id,
                            role="TENANT_ADMIN",
                            created_at=datetime.now(UTC),
                        )
                    )
        print("Bootstrap completed.")  # noqa: T201
    finally:
        await database.dispose()


async def site_build_worker(args: argparse.Namespace) -> None:
    settings = get_settings()
    database = Database(settings)
    worker = SiteBuildWorker(database, settings, WebhookSiteBuildExecutor(settings))
    try:
        if args.once:
            await worker.run_once()
        else:
            await worker.run_forever()
    finally:
        await database.dispose()


def serve(import_string: str, *, host: str, port: int, reload: bool) -> None:
    uvicorn.run(
        import_string,
        host=host,
        port=port,
        reload=reload,
        proxy_headers=False,
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="kanoon")
    commands = root.add_subparsers(dest="command", required=True)
    command = commands.add_parser("bootstrap")
    command.add_argument("--email", required=True)
    command.add_argument("--tenant-name", default="Development School")
    command.add_argument("--tenant-slug")
    command.add_argument("--tenant-domain", default="school.localhost")
    worker_command = commands.add_parser("site-build-worker")
    worker_command.add_argument("--once", action="store_true")
    data_command = commands.add_parser("serve-data-plane")
    data_command.add_argument("--reload", action="store_true")
    control_command = commands.add_parser("serve-control-plane")
    control_command.add_argument("--reload", action="store_true")
    return root


def main() -> None:
    args = parser().parse_args()
    if args.command == "bootstrap":
        asyncio.run(bootstrap(args))
    elif args.command == "site-build-worker":
        asyncio.run(site_build_worker(args))
    elif args.command == "serve-data-plane":
        settings = get_settings()
        serve(
            "app.main:app",
            host=settings.data_plane_host,
            port=settings.data_plane_port,
            reload=args.reload,
        )
    elif args.command == "serve-control-plane":
        settings = get_settings()
        serve(
            "app.control_plane:app",
            host=settings.control_plane_host,
            port=settings.control_plane_port,
            reload=args.reload,
        )


if __name__ == "__main__":
    main()
