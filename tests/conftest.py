from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from app.core.config import Settings
from app.core.database import Database


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    configured = os.getenv("KANOON_TEST_DATABASE_DSN")
    if configured:
        yield configured
        return
    with PostgresContainer("postgres:17.6-alpine", driver="psycopg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session", autouse=True)
def migrated_database(postgres_dsn: str) -> None:
    previous = os.environ.get("KANOON_DATABASE_DSN")
    os.environ["KANOON_DATABASE_DSN"] = postgres_dsn
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    if previous is None:
        os.environ.pop("KANOON_DATABASE_DSN", None)
    else:
        os.environ["KANOON_DATABASE_DSN"] = previous


@pytest.fixture
def settings(postgres_dsn: str) -> Settings:
    return Settings(
        environment="testing",
        database_dsn=postgres_dsn,
        database_pool_size=1,
        database_max_overflow=0,
        signing_key="test-signing-key-that-is-long-enough",
    )


@pytest.fixture
async def owner_engine(postgres_dsn: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(postgres_dsn)
    yield engine
    await engine.dispose()


@pytest.fixture
async def database(settings: Settings) -> AsyncIterator[Database]:
    value = Database(settings)
    yield value
    await value.dispose()
