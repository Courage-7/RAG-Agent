FROM ghcr.io/astral-sh/uv:0.12.1-python3.12-trixie@sha256:f99e4b4328b336749b2371a6b998bfaec35d058f314f906a0d3100313c397a48

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY apps/api/src apps/api/src
COPY apps/worker/src apps/worker/src
COPY packages/core/src packages/core/src

RUN uv sync --frozen --all-packages --no-dev

