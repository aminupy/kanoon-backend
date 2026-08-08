from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings

_ROLE_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class Database:
    """Owns pooled connections and creates transaction-bound sessions.

    The application role is selected inside every transaction. Tenant sessions additionally
    set a transaction-local tenant ID; neither setting can leak through the pool.
    """

    def __init__(self, settings: Settings) -> None:
        if not _ROLE_RE.fullmatch(settings.database_application_role):
            raise ValueError("invalid PostgreSQL application role")
        self.application_role = settings.database_application_role
        self.engine: AsyncEngine = create_async_engine(
            settings.database_dsn.get_secret_value(),
            pool_pre_ping=True,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    async def _set_application_role(self, session: AsyncSession) -> None:
        # Identifier is startup-validated and cannot be parameterized by PostgreSQL.
        await session.execute(text(f'SET LOCAL ROLE "{self.application_role}"'))

    @asynccontextmanager
    async def global_session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session, session.begin():
            await self._set_application_role(session)
            yield session

    @asynccontextmanager
    async def tenant_session(self, tenant_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session, session.begin():
            await self._set_application_role(session)
            await session.execute(
                text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_id)},
            )
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
