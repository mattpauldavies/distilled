.PHONY: dev dev-server dev-client db-up db-down db-reset migrate makemigration test test-coverage

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

makemigration:
	cd server && poetry run alembic revision --autogenerate -m "$(MSG)"

test:
	cd server && poetry run pytest

test-coverage:
	cd server && poetry run pytest --cov=app --cov-report=term-missing
