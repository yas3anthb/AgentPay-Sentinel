.PHONY: help install keys opa test policy-test agent-install agent-test agent-demo lint up down logs demo demo-clean demo-injection dashboard reconcile clean

VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip
OPA  := ./bin/opa

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Create the venv and install dependencies
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

keys: ## Generate the static RS256 delegation keypair (dev only)
	$(PY) scripts/gen_keys.py

opa: ## Fetch the OPA binary used for local policy tests
	@mkdir -p bin
	curl -sSL -o $(OPA) https://openpolicyagent.org/downloads/v1.0.0/opa_linux_amd64_static
	@chmod +x $(OPA)
	@$(OPA) version

policy-test: ## Run the Rego policy unit tests
	$(OPA) check policies/
	$(OPA) test policies/ -v

test: policy-test ## Run the gateway test suite (Python + Rego)
	$(PY) -m pytest -q

agent-install: ## Create the agent simulator's separate venv (its pins conflict with the gateway's)
	python3 -m venv .venv-agent
	.venv-agent/bin/pip install --upgrade pip
	.venv-agent/bin/pip install -r apps/agent-simulator/requirements.txt

agent-test: ## Run the agent simulator's tests
	cd apps/agent-simulator && ../../.venv-agent/bin/python -m pytest -q

agent-demo: ## Run the agent scenarios against the running stack
	@curl -sS -X POST localhost:9200/simulate/reset -o /dev/null
	@echo "--- clean purchase ---"
	@curl -sS -X POST localhost:9200/simulate/clean-purchase -H 'content-type: application/json' -d '{}' | \
	  python3 -c "import json,sys; d=json.load(sys.stdin); print(d['decision'], d['reason_codes'], '| state:', d['sentinel']['state'])"
	@echo "--- adversarial ---"
	@curl -sS -X POST localhost:9200/simulate/adversarial -H 'content-type: application/json' -d '{}' | \
	  python3 -c "import json,sys; d=json.load(sys.stdin); print(d['decision'], d['reason_codes'], '| provider calls:', d['provider_calls']['delta'], '| injection intact:', d['injection']['reached_agent_unmodified'])"

up: ## Start the whole stack (gateway, OPA, Redis, Postgres, provider, agent, dashboard)
	docker compose up --build -d
	@echo "gateway   http://localhost:8080/docs"
	@echo "agent     http://localhost:9200/docs"
	@echo "dashboard http://localhost:8501"
	@echo "provider  http://localhost:9100/healthz"

down: ## Stop the stack and remove volumes
	docker compose down -v

logs: ## Tail the gateway logs
	docker compose logs -f gateway

demo-clean: ## Demo A — a legitimate purchase runs end to end and is ALLOWed
	$(PY) scripts/demo_clean.py

demo-injection: ## Demo B — a poisoned merchant page is BLOCKed before the provider is called
	$(PY) scripts/demo_injection.py

demo: demo-clean demo-injection ## Run both demos

reconcile: ## Resolve UNKNOWN payments by querying the provider
	curl -sS -X POST http://localhost:8080/v1/reconcile | python3 -m json.tool

dashboard: ## Run the dashboard against a locally-running gateway
	$(VENV)/bin/streamlit run dashboard/app.py

clean: ## Remove local artefacts
	rm -rf .pytest_cache **/__pycache__ *.db
