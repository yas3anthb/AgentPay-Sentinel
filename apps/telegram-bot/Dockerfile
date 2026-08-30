FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY apps/telegram-bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/telegram-bot/telegram_bot/ ./telegram_bot/

# Default: long polling, no port. Webhook mode overrides the command to
# `uvicorn telegram_bot.webapp:app` and publishes a port.
CMD ["python", "-m", "telegram_bot.main"]
