.PHONY: format lint typecheck test test-integration migrate migration-check run run-control

format:
	uv run ruff format app tests migrations
	uv run ruff check app tests migrations --fix

lint:
	uv run ruff format --check app tests migrations
	uv run ruff check app tests migrations

typecheck:
	uv run mypy app tests

test:
	uv run pytest -m "not integration"

test-integration:
	uv run pytest -m integration

migrate:
	uv run alembic upgrade head

migration-check:
	uv run alembic check

run:
	uv run kanoon serve-data-plane --reload

run-control:
	uv run kanoon serve-control-plane --reload
