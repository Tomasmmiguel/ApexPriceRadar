# ==============================================================================
# Multi-Stage Production Dockerfile for ApexPrice Engine
# ==============================================================================

# 1. Build Stage
FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# 2. Runtime Stage
FROM python:3.12-slim-bookworm AS runner
WORKDIR /app

# Non-root user for security compliance
RUN useradd -m -u 1001 appuser
USER appuser

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY --chown=appuser:appuser . .

ENTRYPOINT ["python", "main.py"]
CMD ["--query", "PlayStation 5,MacBook", "--retailer", "all"]
