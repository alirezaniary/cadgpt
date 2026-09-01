PYTHON ?= uv run --group dev

.PHONY: verify lint types test contracts

verify: lint types contracts test

lint:
	$(PYTHON) ruff check .
	$(PYTHON) ruff format --check .

types:
	$(PYTHON) mypy --strict engine/

contracts:
	$(PYTHON) lint-imports --no-cache

test:
	$(PYTHON) pytest -q
