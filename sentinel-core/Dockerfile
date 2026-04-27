FROM python:3.12-slim

WORKDIR /app

# Install system deps (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
# Install deps from pyproject.toml for layer caching. Editable installs
# don't work without the source tree, so install deps explicitly here.
RUN pip install --no-cache-dir \
    "fastapi>=0.135.0" \
    "uvicorn[standard]>=0.44.0" \
    "pydantic>=2.7.0" \
    "pydantic-settings>=2.13.0" \
    "httpx>=0.28.1" \
    "tiktoken" \
    "litellm>=1.83.0,<2.0" \
    "tenacity>=8.2.0,<10.0" \
    "anthropic>=0.93.0,<1.0" \
    "numpy>=1.26,<3.0" \
    "PyYAML>=6.0,<7.0"

COPY . .

# Copy shared package from the `shared` build context (declared in compose.yml
# additional_contexts). Lands at /app/sentinel_shared/ so existing PYTHONPATH
# (WORKDIR /app) makes `import sentinel_shared.<module>` resolve.
COPY --from=shared sentinel_shared/ /app/sentinel_shared/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
