#!/bin/bash
# Start the WirelessCommAI project

set -e
cd "$(dirname "$0")/.."

echo "Starting WirelessCommAI..."

# Start backend
echo "Starting backend on http://localhost:8000 ..."
cd backend
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

# Start frontend
echo "Starting frontend on http://localhost:5173 ..."
cd frontend
npm run serve &
FRONTEND_PID=$!
cd ..

echo ""
echo "Backend:  http://localhost:8000/docs"
echo "Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop all services"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
