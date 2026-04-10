FROM python:3.12-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    "discord.py>=2.7.1" \
    "httpx>=0.28.1"

COPY bot.py .

CMD ["python", "bot.py"]
