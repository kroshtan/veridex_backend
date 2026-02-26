FROM python:3.12-slim

# Pull uv from its official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# ── Dependencies (cached layer — only reruns when lock file changes) ──────────
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ── Playwright: install Chromium + all required system libraries ──────────────
RUN uv run playwright install chromium --with-deps

# ── Source code ───────────────────────────────────────────────────────────────
COPY src/ ./src/
RUN uv sync --frozen --no-dev

ENV PYTHONPATH=/app/src
EXPOSE 8080

CMD ["uv", "run", "uvicorn", "veridex.main:app", "--host", "0.0.0.0", "--port", "8080"]
