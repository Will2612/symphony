# syntax=docker/dockerfile:1.7
# Build context is ./python (set by .github/workflows/build-image.yml).

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Non-root user. UID/GID 1000 matches the typical first-host-user on
# Raspberry Pi OS / Ubuntu; the named workspace volume ends up owned
# 1000:1000, which is fine for an isolated Pi host.
RUN groupadd --system --gid 1000 symphony \
    && useradd --system --uid 1000 --gid symphony --no-create-home \
       --shell /usr/sbin/nologin symphony

WORKDIR /app

# Copy full source (tests/, docs/, examples/, .venv/ excluded by .dockerignore).
COPY . /app

# Install runtime deps + the package itself. --no-cache-dir keeps the
# layer small; --no-compile avoids bytecode generation entirely.
RUN pip install --no-cache-dir --no-compile .

# Workspace mount point. The named volume on the host supplies the actual dir.
RUN mkdir -p /var/lib/symphony/workspaces \
    && chown -R symphony:symphony /var/lib/symphony

USER symphony:symphony

# CLI signature per python/README.md:
#   symphony [--port N] <WORKFLOW.md> --i-understand-that-this-will-be-running-without-the-usual-guardrails
# /etc/symphony/{WORKFLOW.md,symphony.env} are bind-mounted from the host
# by docker-compose.yml.
ENTRYPOINT ["symphony"]
CMD ["/etc/symphony/WORKFLOW.md", "--i-understand-that-this-will-be-running-without-the-usual-guardrails"]
