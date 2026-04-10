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
    "tiktoken"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
