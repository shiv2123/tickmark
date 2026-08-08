.PHONY: setup test lint fmt check clean

VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

setup: ## create venv and install in editable mode with dev extras
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip -q
	$(PIP) install -e ".[dev]" -q
	@echo "ready. activate with: source $(VENV)/bin/activate"

test: ## run the test suite
	$(VENV)/bin/pytest

lint: ## static checks
	$(VENV)/bin/ruff check src tests

fmt: ## autoformat
	$(VENV)/bin/ruff format src tests
	$(VENV)/bin/ruff check --fix src tests

# make check PR=42
# make check PR=42 REPO=owner/name
check: ## collect evidence for one real PR and print it
	$(PY) -m tickmark collect --pr $(PR) $(if $(REPO),--repo $(REPO),)

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache dist build *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
