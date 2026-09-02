# One command per gate. `make verify` is what CI runs and what must pass before anything
# is called done.

UV      ?= uv run
API     := services/api
WEB     := services/web
COMPOSE := docker compose -f deploy/compose.yaml

.PHONY: help verify lint format types contracts test test-fast web-verify install \
        migrations migrate run worker shell schema messages compile-messages \
        up down logs reset

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

## ---------------------------------------------------------------- verification

verify: lint types contracts test web-verify  ## Every gate, in the order CI runs them

lint:  ## ruff check and format check
	$(UV) ruff check .
	$(UV) ruff format --check .

format:  ## Apply ruff fixes and formatting
	$(UV) ruff check . --fix
	$(UV) ruff format .

types:  ## mypy --strict over the engine and the service
	$(UV) mypy packages/engine/src $(API)/cadgpt

contracts:  ## The import contracts: I1, engine independence, app layering
	$(UV) lint-imports --no-cache

test:  ## The whole suite, engine and service
	$(UV) pytest

test-fast:  ## Skip the tests that parse real IFC files
	$(UV) pytest -m "not integration"

web-verify:  ## Frontend type check, lint and production build
	cd $(WEB) && pnpm install --frozen-lockfile && pnpm run verify

## ---------------------------------------------------------------- development

install:  ## Sync the Python workspace and the frontend
	uv sync --all-packages
	cd $(WEB) && pnpm install

migrations:  ## Generate migrations for a model change
	cd $(API) && $(UV) --project .. python manage.py makemigrations

migrate:  ## Apply migrations
	cd $(API) && $(UV) --project .. python manage.py migrate

run:  ## Run the API on localhost:8000
	cd $(API) && $(UV) --project .. python manage.py runserver

worker:  ## Run a Celery worker against the checks queue
	cd $(API) && $(UV) --project .. celery -A cadgpt.config.celery worker \
		-Q checks,default -l info

shell:  ## Django shell
	cd $(API) && $(UV) --project .. python manage.py shell

messages:  ## Extract translatable strings into the .po catalogues (needs gettext)
	cd $(API) && $(UV) --project .. python manage.py makemessages -a --ignore=node_modules

compile-messages:  ## Compile the .po catalogues to .mo (needs gettext)
	cd $(API) && $(UV) --project .. python manage.py compilemessages

schema:  ## Regenerate the OpenAPI schema and the frontend's types from it
	cd $(API) && $(UV) --project .. python manage.py spectacular --color --file \
		../../services/web/openapi.yaml
	cd $(WEB) && pnpm run generate:api

## ---------------------------------------------------------------- containers

up:  ## Start Postgres, Redis, the API, a worker and the frontend
	$(COMPOSE) up --build -d

down:  ## Stop everything
	$(COMPOSE) down

reset:  ## Stop everything and delete the volumes
	$(COMPOSE) down -v

logs:  ## Follow the logs
	$(COMPOSE) logs -f
