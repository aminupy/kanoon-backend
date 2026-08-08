FROM ghcr.io/astral-sh/uv:0.11.33-python3.13-trixie-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000 8001
CMD ["uv", "run", "--no-sync", "kanoon", "serve-data-plane"]
