.PHONY: dev dev-server dev-client db-up db-down db-reset migrate create-migration test test-server test-client test-coverage seed-demo seed-reset

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
	docker compose up -d postgres

db-down:
	docker compose down

db-reset:
	docker compose down -v && docker compose up -d postgres

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
