FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OTOMAI_ENV_DIR=/app/env

# Use the reviewed lock rather than resolving new exchange-library versions during deployment.
COPY pyproject.toml uv.lock README.md /app/
RUN uv export --locked --no-dev --no-emit-project --output-file /tmp/requirements.txt >/dev/null && \
    uv pip install --system --require-hashes -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

COPY dist/*.whl /tmp/otomai-wheels/
RUN python -c 'import glob; assert len(glob.glob("/tmp/otomai-wheels/*.whl")) == 1, "Expected one wheel; rebuild using uv build --clear"' && \
    uv pip install --system --no-deps /tmp/otomai-wheels/*.whl && \
    uv pip check --system && \
    rm -rf /tmp/otomai-wheels
COPY conf/ /app/conf/
ENTRYPOINT ["otomai"]
