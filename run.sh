#!/usr/bin/env bash
set -e

# ─── Face Attendance System — One-Click Run ───
# Creates venv, installs deps, seeds DB, starts server.

cd "$(dirname "$0")"

echo "=========================================="
echo "  Face Attendance System v2.0"
echo "=========================================="
echo ""

PYTHON=python3
if ! command -v $PYTHON &>/dev/null; then
    PYTHON=python
fi
if ! command -v $PYTHON &>/dev/null; then
    echo "ERROR: Python 3 not found. Install Python 3.10+ first."
    exit 1
fi

PYVER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python detected: $PYVER ($PYTHON)"

# ── Step 1: Virtual environment ──
if [ ! -d "venv" ]; then
    echo "[1/4] Creating virtual environment..."
    $PYTHON -m venv venv
fi
. venv/bin/activate
echo "[1/4] Virtual environment ready."

# ── Step 2: System deps (Linux only, best-effort) ──
if [ -f /etc/os-release ]; then
    echo "[2/4] Installing system libraries (may need sudo)..."
    sudo apt-get update -qq 2>/dev/null || true
    sudo apt-get install -y -qq \
        libgl1 libglib2.0-0 libgomp1 \
        libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 \
        libffi-dev libcairo2 libpq-dev pkg-config 2>/dev/null || true
fi
echo "[2/4] System libraries ready."

# ── Step 3: Python packages ──
echo "[3/4] Installing Python packages (this may take a few minutes)..."
pip install --upgrade pip -q
pip install -r requirements.txt -q 2>&1 | tail -1
echo "[3/4] Python packages installed."

# ── Step 4: Start server ──
echo ""
echo "=========================================="
echo "  Server starting!"
echo "  http://localhost:5000"
echo "  Login: admin / admin123"
echo "=========================================="
echo ""

export FLASK_ENV=development
exec $PYTHON -c "
from app import create_app
app = create_app()
app.run(host='0.0.0.0', port=5000, debug=False)
"
