#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# FluxRules — One-time project setup
# Run once after cloning. Sets up backend Python env + frontend npm packages.
# ─────────────────────────────────────────────────────────────────────────────
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${CYAN}[setup]${NC} $*"; }
success() { echo -e "${GREEN}[setup]${NC} $*"; }
error()   { echo -e "${RED}[setup] ERROR:${NC} $*"; exit 1; }

echo ""
echo "  ███████╗██╗     ██╗   ██╗██╗  ██╗██████╗ ██╗   ██╗██╗     ███████╗███████╗"
echo "  ██╔════╝██║     ██║   ██║╚██╗██╔╝██╔══██╗██║   ██║██║     ██╔════╝██╔════╝"
echo "  █████╗  ██║     ██║   ██║ ╚███╔╝ ██████╔╝██║   ██║██║     █████╗  ███████╗"
echo "  ██╔══╝  ██║     ██║   ██║ ██╔██╗ ██╔══██╗██║   ██║██║     ██╔══╝  ╚════██║"
echo "  ██║     ███████╗╚██████╔╝██╔╝ ██╗██║  ██║╚██████╔╝███████╗███████╗███████║"
echo "  ╚═╝     ╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚══════╝╚══════╝"
echo ""
info "Starting project setup…"
echo ""

# ── 1. Backend (Python / uv) ──────────────────────────────────────────────────
info "── Backend setup ─────────────────────────────────────────────────────────"

if ! command -v uv &>/dev/null; then
    info "uv not found — installing…"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

cd "$ROOT/backend"
info "Installing Python dependencies (uv sync)…"
uv sync --extra dev

info "Initialising database…"
uv run python -c "from app.database import init_db; init_db()"

info "Running backend test suite…"
uv run pytest --tb=short -q

success "Backend ready ✓"
echo ""

# ── 2. Frontend (Node / npm) ──────────────────────────────────────────────────
info "── Frontend setup ────────────────────────────────────────────────────────"

if ! command -v node &>/dev/null; then
    error "Node.js not found. Install it from https://nodejs.org/ and re-run setup."
fi
if ! command -v npm &>/dev/null; then
    error "npm not found. Install Node.js from https://nodejs.org/ and re-run setup."
fi

NODE_VER=$(node --version)
NPM_VER=$(npm --version)
info "Node $NODE_VER / npm $NPM_VER detected"

cd "$ROOT/frontend"
info "Installing npm dependencies…"
npm install

info "Building frontend for production…"
npm run build

success "Frontend ready ✓"
echo ""

# ── 3. Summary ────────────────────────────────────────────────────────────────
echo "──────────────────────────────────────────────────────────────────────────"
success "Setup complete! 🎉"
echo ""
  echo "  Run modes:"
  echo "    ./run.sh              → API + frontend dev server (hot reload)"
  echo "    ./run.sh api          → backend only"
  echo "    ./run.sh frontend     → frontend dev server only"
  echo "    ./run.sh install      → reinstall / update all dependencies"
  echo "    ./run.sh build        → production frontend build → frontend/dist/"
  echo "    ./run.sh docker       → full stack via Docker Compose"
  echo "    ./run.sh stop         → kill dev servers on ports 8000 & 5173"
echo ""
echo "  URLs (dev):"
echo "    Frontend  → http://localhost:5173"
echo "    API       → http://localhost:8000"
echo "    API Docs  → http://localhost:8000/docs"
echo ""
echo "  URLs (Docker):"
echo "    Frontend  → http://localhost:8080"
echo "    API       → http://localhost:8000"
echo ""