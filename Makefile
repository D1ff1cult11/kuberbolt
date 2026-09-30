.PHONY: up down api frontend lnd help

help:
	@echo "Kuberbolt Development Commands:"
	@echo "  make up       - Start the entire local stack (LND, API, Frontend)"
	@echo "  make down     - Stop all running services"
	@echo "  make api      - Start only the FastAPI backend"
	@echo "  make frontend - Start only the React frontend"
	@echo "  make lnd      - Start only the Lightning nodes via Docker"

up:
	@echo "🚀 Starting Lightning Infrastructure..."
	@cd lightning-infra && docker compose -f docker-compose.lnd.yml up -d
	@echo "🚀 Starting FastAPI Backend (in background)..."
	@start pwsh -NoExit -Command "uvicorn api.main:app --reload --port 8000"
	@echo "🚀 Starting Frontend Dashboard (in background)..."
	@start pwsh -NoExit -Command "cd frontend; $$env:VITE_API_URL='http://localhost:8000'; npm run dev"
	@echo "✅ All systems go! Dashboard available at http://localhost:5173"

down:
	@echo "🛑 Stopping Lightning Infrastructure..."
	@cd lightning-infra && docker compose -f docker-compose.lnd.yml down
	@echo "🛑 Please close the API and Frontend terminal windows manually."

api:
	uvicorn api.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

lnd:
	cd lightning-infra && docker compose -f docker-compose.lnd.yml up -d
