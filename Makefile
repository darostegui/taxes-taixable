.DEFAULT_GOAL := help
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help venv install test lint run db-up db-down es-up

help:
	@echo "Targets: venv install test lint run db-up db-down es-up"

venv:
	python3 -m venv $(VENV)

install: venv
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"

test:
	$(VENV)/bin/pytest -q

lint:
	$(VENV)/bin/ruff check src tests

run:
	$(VENV)/bin/uvicorn taixable_copilot.api.app:app --reload --port 8080

db-up:
	docker compose up -d mysql

db-down:
	docker compose down

es-up:
	docker compose up -d elasticsearch
