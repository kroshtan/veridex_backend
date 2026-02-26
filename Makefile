.PHONY: help test
.DEFAULT_GOAL := help

VENV_DIR = ./.venv
PYTHON = $(VENV_DIR)/bin/python

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = "(: ).*?## "}; {sub("Makefile:", "", $$1); printf "\033[36m%-37s\033[0m %s\n", $$1, $$2}'

clean: clean-build clean-pyc clean-test clean-venv  ## Remove build, test, coverage and Python artifacts (including venv)

clean-build: ## Remove build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf .eggs/
	find . -name '*.egg-info' -exec rm -rf {} +
	find . -name '*.egg' -exec rm -rf {} +

clean-pyc: ## Remove Python file artifacts
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -rf {} +

clean-test:  ## Remove test and coverage artifacts
	find . -name '*,cover' -exec rm -f {} +
	rm -f .coverage
	rm -f coverage.xml
	rm -rf htmlcov/
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache

clean-venv: ## Remove venv
	rm -rf $(VENV_DIR)

create-venv:  ## Create Python venv if it does not exist
	test -d $(VENV_DIR) || python -m venv $(VENV_DIR) && $(VENV_DIR)/bin/pip install --upgrade pip uv

compile-requirements: create-venv ## Compile requirements
	$(PYTHON) -m uv lock

install: create-venv  ## Install dependencies
	$(PYTHON) -m uv sync --all-groups
	$(PYTHON) -m uv pip install --no-deps -e .
	$(VENV_DIR)/bin/pre-commit install

install-ci:  ## Install package and all its requirements for development
	uv sync --all-groups
	uv pip install --no-deps -e .

fix:  ## Run pre-commit on all files
	$(VENV_DIR)/bin/pre-commit run --all-files

test:  ## Run tests
	uv run pytest .

test-unit:  ## Run unit tests
	uv run pytest tests/unit

test-integration:  ## Run integration tests
	uv run pytest tests/integration

show-coverage:  ## Open the coverage report in the default browser
	@xdg-open htmlcov/index.html || open htmlcov/index.html

run-local:  ## Run the app locally
	PYTHONPATH=src $(PYTHON) src/veridex/main.py

dev-start: ## Start unoserver (runs in background)
	@echo "Starting unoserver..."
	@./scripts/unoserver.sh start
	@echo ""
	@echo "✓ Unoserver is running"

dev-stop: ## Stop unoserver
	@./scripts/unoserver.sh stop

dev-status: ## Check if unoserver is running
	@./scripts/unoserver.sh status

dev-logs: ## View unoserver logs
	@./scripts/unoserver.sh logs
