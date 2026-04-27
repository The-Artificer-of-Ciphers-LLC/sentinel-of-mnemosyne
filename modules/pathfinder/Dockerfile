FROM python:3.12-slim

WORKDIR /app

# curl required for the compose.yml healthcheck CMD
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "fastapi>=0.135.0" \
    "uvicorn[standard]>=0.44.0" \
    "httpx>=0.28.1" \
    "litellm>=1.83.0" \
    "pydantic-settings>=2.13.0" \
    "pyyaml>=6.0.0" \
    "rapidfuzz>=3.14.0" \
    "reportlab>=4.4.0" \
    "beautifulsoup4>=4.12.0" \
    "numpy>=1.26.0"

COPY . .

# Copy shared package from the `shared` build context (declared in compose.yml
# additional_contexts). Lands at /app/sentinel_shared/ so existing PYTHONPATH
# (WORKDIR /app) makes `import sentinel_shared.<module>` resolve.
COPY --from=shared sentinel_shared/ /app/sentinel_shared/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
