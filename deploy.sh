#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Overlap Annotation App — Deployment Script
# ============================================================
# Usage:
#   1. Copy the project to the server
#   2. Run: bash deploy.sh
#
# Environment variables (optional):
#   PORT          — port to listen on (default: 5000)
#   HOST          — bind address (default: 0.0.0.0)
#   WORKERS       — gunicorn worker count (default: 2)
#   SECRET_KEY    — Flask session secret (auto-generated if not set)
#   EXPORT_DIR    — directory for auto-exported annotation files
# ============================================================

PORT="${PORT:-5000}"
HOST="${HOST:-0.0.0.0}"
WORKERS="${WORKERS:-2}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Overlap Annotation App Deployment ==="
echo "Project dir: $SCRIPT_DIR"

# 1. Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install Python 3.10+."
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python version: $PY_VERSION"

# 2. Create venv if needed
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# 3. Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip -q
pip install -e "$SCRIPT_DIR" -q
pip install gunicorn -q

# 4. Check required files
if [ ! -d "$SCRIPT_DIR/selected_audios" ]; then
    echo "WARNING: selected_audios/ directory not found. Audio playback will not work."
fi

if [ ! -f "$SCRIPT_DIR/annotations.db" ]; then
    echo "No existing database found. A new one will be created on first run."
fi

# 5. Generate a stable secret key if not set
SECRET_KEY_FILE="$SCRIPT_DIR/.secret_key"
if [ -z "${SECRET_KEY:-}" ]; then
    if [ -f "$SECRET_KEY_FILE" ]; then
        export SECRET_KEY=$(cat "$SECRET_KEY_FILE")
    else
        export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        echo "$SECRET_KEY" > "$SECRET_KEY_FILE"
        chmod 600 "$SECRET_KEY_FILE"
        echo "Generated new SECRET_KEY (saved to .secret_key)"
    fi
fi

# 6. Run with gunicorn
echo ""
echo "Starting server on http://$HOST:$PORT"
echo "Workers: $WORKERS"
echo "Press Ctrl+C to stop."
echo ""

exec gunicorn \
    --bind "$HOST:$PORT" \
    --workers "$WORKERS" \
    --access-logfile - \
    --error-logfile - \
    --timeout 120 \
    "webapp.app:app"
