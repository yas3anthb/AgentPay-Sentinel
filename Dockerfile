# One image, three entrypoints (gateway, control plane, mock provider). Keeping
# them identical means the demo can't drift between what the control plane
# signs, what the gateway verifies, and what the provider checks.
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
COPY control_plane/ ./control_plane/
COPY mock_provider/ ./mock_provider/
COPY scripts/ ./scripts/
COPY policies/ ./policies/

# Keypairs are generated on first boot by the keygen service if not mounted in.
RUN mkdir -p keys

EXPOSE 8080 8090 9100

CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8080"]
