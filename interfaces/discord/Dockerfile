FROM python:3.12-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    "discord.py>=2.7.1" \
    "httpx>=0.28.1"

# Build context is repo root (../.. from interfaces/discord/)
# Copy shared library first so it's available to bot.py
COPY shared/ /app/shared/
COPY interfaces/discord/ /app/

CMD ["python", "bot.py"]
