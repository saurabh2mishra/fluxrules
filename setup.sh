#!/bin/bash

set -e

echo "Setting up FluxRules Platform..."

cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "Running tests..."
pytest

echo "Initializing database..."
python -c "from app.database import init_db; init_db()"

echo "Setup complete!"
echo "To run without Docker:"
echo "  Terminal 1: cd backend && source venv/bin/activate && uvicorn app.main:app --reload"
echo "  Terminal 2: cd backend && source venv/bin/activate && python -m app.workers.event_worker"
echo "  Terminal 3: redis-server"
echo ""
echo "To run with Docker:"
echo "  docker-compose up --build"