# One image serves the SPA and the API: the SPA is built first and copied
# into the API image as static files. The SPA build runs on the builder's
# own platform, since its output is the same static files everywhere.

FROM --platform=$BUILDPLATFORM node:24-alpine AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY contracts/ /src/contracts/
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS api-build
COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY api/pyproject.toml api/uv.lock api/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY api/ ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
RUN useradd --system --uid 10001 --home-dir /app app
WORKDIR /app
COPY --from=api-build --chown=app:app /app /app
COPY --from=web --chown=app:app /src/web/dist /app/static
ENV PATH="/app/.venv/bin:$PATH" STATIC_DIR=/app/static PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
# Migrations run before the server starts; alembic is idempotent at head.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn plandesk.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
