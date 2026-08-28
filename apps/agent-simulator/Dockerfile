# Its own image, for the same reason it has its own requirements file: the
# agent frameworks and the gateway pin incompatible versions of pydantic and
# the OpenAI SDK.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY apps/agent-simulator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && apt-get purge -y build-essential && apt-get autoremove -y

COPY apps/agent-simulator/agent_simulator/ ./agent_simulator/

EXPOSE 9200

CMD ["uvicorn", "agent_simulator.main:app", "--host", "0.0.0.0", "--port", "9200"]
