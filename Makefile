.PHONY: up down lnd help

help:
	@echo "Kuberbolt Development Commands:"
	@echo "  make up       - Start the Lightning nodes via Docker"
	@echo "  make down     - Stop the Lightning nodes"
	@echo "  make lnd      - Same as make up"

up: lnd

down:
	@echo "🛑 Stopping Lightning Infrastructure..."
	@cd lightning-infra && docker compose -f docker-compose.lnd.yml down

lnd:
	cd lightning-infra && docker compose -f docker-compose.lnd.yml up -d
