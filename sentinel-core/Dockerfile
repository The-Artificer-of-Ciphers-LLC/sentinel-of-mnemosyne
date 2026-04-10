FROM python:3.12-slim

WORKDIR /app

# Install system deps (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
# Install deps before copying source for layer caching. Keep in sync with pyproject.toml.
RUN pip install --no-cache-dir \
        "fastapi>=0.135.0" \
        "uvicorn[standard]>=0.44.0" \
        "pydantic>=2.7.0" \
        "pydantic-settings>=2.13.0" \
        "httpx>=0.28.1" \
        "tiktoken" \
        "litellm>=1.83.0,<2.0" \
        "tenacity>=8.2.0,<10.0" \
        "anthropic>=0.93.0,<1.0"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
