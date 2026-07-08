FROM python:3.12-slim

WORKDIR /app

# curl required for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "fastapi>=0.135.0" \
    "uvicorn[standard]>=0.44.0" \
    "httpx>=0.28.1" \
    "pydantic-settings>=2.13.0" \
    "pyyaml>=6.0.0"

COPY . .

# Copy shared package from the `shared` build context (declared in compose.yml
# additional_contexts). Lands at /app/sentinel_shared/ so existing PYTHONPATH
# (WORKDIR /app) makes `import sentinel_shared.<module>` resolve.
COPY --from=shared sentinel_shared/ /app/sentinel_shared/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
