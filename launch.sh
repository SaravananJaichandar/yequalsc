#!/bin/bash
# y=c Launch Script
# Starts all required services for the y=c private second brain

echo "=========================================="
echo "  y=c - Your Private Second Brain"
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Cleanup on exit
cleanup() {
    echo ""
    echo "Stopping services..."
    [ -n "$BACKEND_PID" ] && kill $BACKEND_PID 2>/dev/null
    [ -n "$WATCHER_PID" ] && kill $WATCHER_PID 2>/dev/null
    echo "All services stopped."
}
trap cleanup EXIT INT TERM

# Start backend
echo "[1/3] Starting FastAPI backend..."
python3 -m backend.yc_server &
BACKEND_PID=$!

# Wait for backend to be ready
echo "  Waiting for backend..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "  Backend ready."
        break
    fi
    sleep 1
done

# Start file watcher (watches ~/Downloads for exports)
echo "[2/3] Starting file watcher..."
python3 backend/file_watcher.py &
WATCHER_PID=$!

# Open app
echo "[3/3] Starting Tauri app..."
cd app && npm run tauri dev
