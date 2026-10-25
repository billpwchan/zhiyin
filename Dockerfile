# The server image: web app, YouTube Music lookups, Claude for the editor. The audio model is not here; it runs on
# a Mac (`zhiyin worker`) that sends the server its vectors.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy DISABLE_AUTOUPDATER=1 TZ=UTC
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /usr/local/bin/uv

RUN useradd --create-home --uid 1000 app
USER app
WORKDIR /app

# Claude Code runs the editor steps (`claude -p`) when the server has a token or an API key; otherwise the owner's
# calls go to the Mac worker (docs/self-hosting.md, "Whose Claude").
ARG CLAUDE_VERSION=2.1.310
RUN curl -fsSL https://claude.ai/install.sh | bash -s ${CLAUDE_VERSION}
ENV PATH=/home/app/.local/bin:/app/.venv/bin:$PATH

COPY --chown=app pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --no-install-project
COPY --chown=app zhiyin ./zhiyin
COPY --chown=app web ./web
COPY --chown=app demo ./demo
COPY --chown=app README.md LICENSE ./
RUN uv sync --frozen --no-default-groups

ENV ZHIYIN_DATA=/data ZHIYIN_AUTH=1 ZHIYIN_AUDIO=remote ZHIYIN_LLM_CONCURRENCY=2
EXPOSE 8817
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://127.0.0.1:8817/healthz || exit 1
CMD ["uvicorn", "zhiyin.server:app", "--host", "0.0.0.0", "--port", "8817", "--proxy-headers", "--forwarded-allow-ips", "*"]
