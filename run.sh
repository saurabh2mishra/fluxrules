#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# FluxRules — Development Runner
#
# Usage:
#   ./run.sh              → full stack  (API + frontend dev server, hot-reload)
#   ./run.sh api          → backend only
#   ./run.sh frontend     → frontend dev server only
#   ./run.sh install      → install / update all dependencies (npm + uv)
#   ./run.sh build        → production frontend build  →  frontend/dist/
#   ./run.sh docker       → full stack via Docker Compose
#   ./run.sh stop         → kill any process on ports 8000 & 5173
#
# First time?  Run ./setup.sh once, then ./run.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[FluxRules]${NC} $*"; }
success() { echo -e "${GREEN}✔ [FluxRules]${NC} $*"; }
warn()    { echo -e "${YELLOW}⚠ [FluxRules]${NC} $*"; }
error()   { echo -e "${RED}✘ [FluxRules] ERROR:${NC} $*"; exit 1; }

MODE="${1:-all}"

# ── Free a TCP port ────────────────────────────────────────────────────
free_port() {
    local pids
    pids=$(lsof -ti:"$1" 2>/dev/null) || true
    [ -n "$pids" ] && echo "$pids" | xargs kill -9 2>/dev/null || true
}

# ── Stop mode ─────────────────────────────────────────────────────────────────
if [ "$MODE" = "stop" ]; then
    info "Stopping FluxRules servers (ports 8000 & 5173)…"
    free_port 8000
    free_port 5173
    success "Done."
    exit 0
fi

# ── Docker mode ───────────────────────────────────────────────────────────────
if [ "$MODE" = "docker" ]; then
    command -v docker &>/dev/null || error "Docker not found. Install from https://docs.docker.com/get-docker/"
    info "Starting full stack via Docker Compose…"
    info "  Frontend (Nginx) → http://localhost:8080"
    info "  API              → http://localhost:8000"
    info "  API Docs         → http://localhost:8000/docs"
    echo ""
    cd "$ROOT"
    docker-compose up --build
    exit 0
fi

# ── Install / update all dependencies ─────────────────────────────────────────
if [ "$MODE" = "install" ]; then
    info "Installing / updating all dependencies…"
    echo ""

    # Backend
    command -v uv &>/dev/null || {
        info "uv not found — installing…"
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.cargo/bin:$PATH"
    }
    info "[backend] uv sync…"
    cd "$ROOT/backend" && uv sync --extra dev
    success "Backend dependencies ready."

    # Frontend
    command -v node &>/dev/null || error "Node.js not found. Install from https://nodejs.org/"
    command -v npm  &>/dev/null || error "npm not found. Install Node.js from https://nodejs.org/"
    info "[frontend] npm install…"
    cd "$ROOT/frontend" && npm install
    success "Frontend dependencies ready."

    echo ""
    success "All dependencies installed. Run './run.sh' to start the dev stack."
    exit 0
fi

# ── Production build ──────────────────────────────────────────────────────────
if [ "$MODE" = "build" ]; then
    command -v npm &>/dev/null || error "'npm' not found. Install Node.js from https://nodejs.org/"
    info "Building frontend for production…"
    cd "$ROOT/frontend"
    [ -d node_modules ] || npm install
    npm run build
    success "Frontend built → frontend/dist/"
    exit 0
fi

# ── Check prerequisites for dev modes ─────────────────────────────────────────
command -v uv  &>/dev/null || error "'uv' not found.  Run: curl -LsSf https://astral.sh/uv/install.sh | sh"
command -v npm &>/dev/null || error "'npm' not found. Install Node.js from https://nodejs.org/"

# ── Backend ───────────────────────────────────────────────────────────────────
start_api() {
    info "Starting FastAPI backend on :8000…"
    free_port 8000
    cd "$ROOT/backend"
    # Bootstrap venv if missing
    if [ ! -f ".venv/bin/activate" ]; then
        warn "No virtualenv found — running 'uv sync --extra dev'…"
        uv sync --extra dev
    fi
    source .venv/bin/activate
    uv run uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000
}

# ── Frontend ──────────────────────────────────────────────────────────────────
start_frontend() {
    info "Starting React frontend dev server on :5173…"
    free_port 5173
    cd "$ROOT/frontend"
    if [ ! -d node_modules ]; then
        warn "node_modules missing — running 'npm install'…"
        npm install
    fi
    npm run dev
}

# ── Mode dispatch ─────────────────────────────────────────────────────────────
case "$MODE" in
  api)
    start_api
    ;;

  frontend)
    start_frontend
    ;;

  all|*)
    echo ""
    info "┌─────────────────────────────────────────────────────┐"
    info "│  FluxRules — Full Development Stack                  │"
    info "│                                                       │"
    info "│  Frontend  →  http://localhost:5173                  │"
    info "│  API       →  http://localhost:8000                  │"
    info "│  Swagger   →  http://localhost:8000/docs             │"
    info "└─────────────────────────────────────────────────────┘"
    echo ""

    (start_api) &
    API_PID=$!
    sleep 2
    (start_frontend) &
    FRONTEND_PID=$!

    trap "kill \$API_PID \$FRONTEND_PID 2>/dev/null; info 'Servers stopped.'" INT TERM
    success "Both servers running. Press Ctrl-C to stop."
    wait
    ;;
esac