#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "=========================================="
echo "  🎓 Face Attendance System v2.0"
echo "=========================================="

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "[1/3] Creating virtual environment..."
    python3 -m venv venv
    . venv/bin/activate
    echo "[2/3] Installing dependencies (~2 min)..."
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
else
    . venv/bin/activate
fi

echo "[3/3] Starting server..."
echo ""
echo "  ✅ Server starting!"
echo "  → http://localhost:5000"
echo "  → Login: admin / admin123"
echo ""

export FLASK_ENV=development
python -c "from app import create_app; app = create_app(); app.run(host='0.0.0.0', port=5000, debug=False)"
