.PHONY: dev dev-server dev-client

dev:
	@trap 'kill 0' EXIT; \
	$(MAKE) dev-server & \
	$(MAKE) dev-client & \
	wait

dev-server:
	cd server && poetry run uvicorn server.main:app --reload --port 8000

dev-client:
	cd client && source ~/.nvm/nvm.sh && nvm use && npm run dev
