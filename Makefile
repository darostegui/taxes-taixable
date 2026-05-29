.DEFAULT_GOAL := help
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help venv install test lint evals run docker-build db-up db-down es-up ingest

help:
	@echo "Targets: venv install test lint evals run docker-build db-up db-down es-up ingest"

venv:
	python3 -m venv $(VENV)

install: venv
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"

test:
	$(VENV)/bin/pytest -q

lint:
	$(VENV)/bin/ruff check src tests scripts evals

evals:
	$(PY) evals/run_evals.py

run:
	$(VENV)/bin/uvicorn taixable_copilot.api.app:app --reload --port 8080

docker-build:
	docker build -t taixable-copilot .

ingest:
	$(PY) scripts/ingest_elastic.py

db-up:
	docker compose up -d mysql

db-down:
	docker compose down

es-up:
	docker compose up -d elasticsearch
