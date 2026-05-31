#!/bin/bash
# Initialize the WirelessCommAI project

set -e

echo "=== WirelessCommAI Initialization ==="

cd "$(dirname "$0")/.."

echo "[1/4] Installing Python dependencies..."
cd backend
pip install -r requirements.txt
cd ..

echo "[2/4] Setting up environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  Created .env from .env.example - please edit with your settings"
fi
if [ ! -f backend/.env ]; then
    cp backend/.env.example backend/.env
    echo "  Created backend/.env from .env.example - please edit with your settings"
fi

echo "[3/4] Installing frontend dependencies..."
cd frontend
npm install
cd ..

echo "[4/4] Initializing database..."
cd backend
python scripts/init_database.py
cd ..

echo "=== Initialization complete ==="
echo "Run: bash scripts/start.sh"
