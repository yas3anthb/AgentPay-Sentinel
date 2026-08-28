# One image, three entrypoints (gateway, mock provider, dashboard). Keeping
# them identical means the demo can't drift between what the gateway signs and
# what the provider verifies.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway/ ./gateway/
COPY mock_provider/ ./mock_provider/
COPY dashboard/ ./dashboard/
COPY scripts/ ./scripts/
COPY policies/ ./policies/

# The delegation keypair is generated on first boot if it isn't mounted in.
RUN mkdir -p keys

EXPOSE 8080 9100 8501

CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8080"]
