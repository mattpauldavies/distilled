.PHONY: help dev dev-server dev-client db-up db-down db-reset migrate create-migration test test-server test-client test-coverage seed-demo seed-reset seed-claim lint lint-server lint-client format format-server format-client smoke-install smoke-test website-install website-build website-serve

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "Development"
	@echo "  dev               Start server and client in parallel"
	@echo "  dev-server        Start the FastAPI server with hot reload"
	@echo "  dev-client        Start the Vite client with hot reload"
	@echo ""
	@echo "Database"
	@echo "  db-up             Start Postgres and pgweb via Docker"
	@echo "  db-down           Stop Docker services"
	@echo "  db-reset          Wipe and restart the database"
	@echo "  migrate           Run pending Alembic migrations"
	@echo "  create-migration  Auto-generate a migration (MSG=<description>)"
	@echo ""
	@echo "Testing"
	@echo "  test              Run all tests (server + client)"
	@echo "  test-server       Run server tests with pytest"
	@echo "  test-client       Run client tests with vitest"
	@echo "  test-coverage     Run all tests with coverage reports"
	@echo ""
	@echo "Seeding"
	@echo "  seed-demo         Seed database with realistic demo data"
	@echo "  seed-reset        Remove all demo data from the database"
	@echo "  seed-claim        Link your Clerk user to seed data (USER=<id>)"
	@echo ""
	@echo "Linting & Formatting"
	@echo "  lint              Lint server and client"
	@echo "  lint-server       Lint server with ruff and mypy"
	@echo "  lint-client       Lint client with eslint"
	@echo "  format            Format server and client"
	@echo "  format-server     Format server with ruff"
	@echo "  format-client     Format client with prettier"
	@echo ""
	@echo "Smoke Tests"
	@echo "  smoke-install     Install Playwright and Chromium"
	@echo "  smoke-test        Run Playwright smoke tests (ARGS=<options>)"
	@echo ""
	@echo "Website"
	@echo "  website-build     Build the marketing website"
	@echo "  website-serve     Serve the website locally with live reload"

dev:
	@trap 'kill 0' EXIT; \
	$(MAKE) dev-server & \
	$(MAKE) dev-client & \
	wait

dev-server:
	cd server && poetry run uvicorn app.main:app --reload --port 8000

dev-client:
	cd client && source ~/.nvm/nvm.sh && nvm use && npm run dev

db-up:
	docker compose up -d postgres pgweb

db-down:
	docker compose down

db-reset:
	docker compose down -v && docker compose up -d postgres pgweb

migrate:
	cd server && poetry run alembic upgrade head

create-migration:
	cd server && poetry run alembic revision --autogenerate -m "$(MSG)"

test: test-server test-client

test-server:
	cd server && poetry run pytest

test-client:
	cd client && source ~/.nvm/nvm.sh && nvm use && npm test

test-coverage:
	cd server && poetry run pytest --cov=app --cov-report=term-missing
	cd client && source ~/.nvm/nvm.sh && nvm use && npm run test:coverage

seed-demo:  ## Seed the database with realistic demo data
	cd server && PYTHONPATH=. poetry run python scripts/seed_demo.py

seed-reset:  ## Remove all demo data from the database
	cd server && PYTHONPATH=. poetry run python scripts/reset_demo.py

seed-claim:  ## Link your Clerk user to seed data: make seed-claim USER=user_abc123
	@test -n "$(USER)" || (echo "Usage: make seed-claim USER=<clerk_user_id>" && exit 1)
	cd server && PYTHONPATH=. poetry run python scripts/claim_seed_data.py $(USER)

lint: lint-server lint-client

lint-server:
	cd server && poetry run ruff check . && poetry run mypy app

lint-client:
	cd client && npm run lint

format: format-server format-client

format-server:
	cd server && poetry run ruff format .

format-client:
	cd client && npm run format

smoke-install:  ## Install Playwright and download Chromium browser
	cd e2e && npm install && npx playwright install --with-deps chromium

smoke-test:  ## Run Playwright smoke tests against the running app (default: http://localhost:5173)
	cd e2e && npx playwright test $(ARGS)

website-build:  ## Build the website to website/_site/
	cd website && npm run build

website-serve:  ## Serve the website locally with live reload
	cd website && npm run serve
