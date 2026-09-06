# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.13
ARG UV_VERSION=0.11.33

# ─────────────────────────────────────────────────────────────
# Builder
# ─────────────────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:${UV_VERSION}-python${PYTHON_VERSION}-trixie-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_PROGRESS=1

WORKDIR /app

# Dependency layer.
# Changes to application source won't invalidate this layer.
COPY pyproject.toml uv.lock README.md ./

RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv sync \
        --frozen \
        --no-dev \
        --no-install-project

# Copy application only after dependencies.
COPY app ./app

# Install the actual project.
# --no-editable is preferable for production deployments.
RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    uv sync \
        --frozen \
        --no-dev \
        --no-editable


# ─────────────────────────────────────────────────────────────
# Runtime
# ─────────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-trixie AS runtime

ARG VCS_REF=unknown

LABEL org.opencontainers.image.revision=$VCS_REF

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

# Non-root runtime user.
RUN groupadd --gid 10001 appuser \
    && useradd \
        --uid 10001 \
        --gid 10001 \
        --no-create-home \
        --home-dir /nonexistent \
        --shell /usr/sbin/nologin \
        appuser

# Only the built Python environment enters the runtime image.
COPY --from=builder /app/.venv /app/.venv

# Runtime files.
COPY --chown=10001:10001 app ./app
COPY --chown=10001:10001 alembic.ini ./
COPY --chown=10001:10001 migrations ./migrations

USER 10001:10001

EXPOSE 8000 8001

CMD ["kanoon", "serve-data-plane"]
