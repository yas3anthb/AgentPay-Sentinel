FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY apps/event-relay/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/event-relay/event_relay/ ./event_relay/

EXPOSE 9300
CMD ["uvicorn", "event_relay.main:app", "--host", "0.0.0.0", "--port", "9300"]
