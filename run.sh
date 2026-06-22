#!/usr/bin/env bash
# Launch the OEM Award Tracker website locally.
# - Creates the virtualenv and installs dependencies on first run.
# - Serves on http://localhost:8501 and prints a Network URL you can open
#   from your phone/another device on the same WiFi.
set -e
cd "$(dirname "$0")"

PY=python3
VENV=".venv"

if [ ! -d "$VENV" ]; then
  echo "First run: creating virtual environment + installing dependencies..."
  "$PY" -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r requirements.txt
fi

# Populate data on first launch if no processed dataset exists yet.
if [ ! -f "data/processed/all_awards_processed.csv" ]; then
  echo "No data yet — running an initial USAspending refresh (this can take a few minutes)..."
  "$VENV/bin/python" refresh.py || echo "Refresh hit issues; starting app with whatever data is available."
fi

# Suppress Streamlit's first-run email prompt (it would otherwise block startup).
if [ ! -f "$HOME/.streamlit/credentials.toml" ]; then
  mkdir -p "$HOME/.streamlit"
  printf '[general]\nemail = ""\n' > "$HOME/.streamlit/credentials.toml"
fi

echo ""
echo "Starting the OEM Award Tracker..."
echo "  • On this Mac:        http://localhost:8501"
echo "  • From your phone:    look for the 'Network URL' printed below"
echo "    (phone must be on the same WiFi; approve the macOS firewall prompt if asked)"
echo ""

# 0.0.0.0 makes it reachable from other devices on the LAN; browser opens automatically.
exec "$VENV/bin/streamlit" run app.py \
  --server.address 0.0.0.0 \
  --server.port 8501 \
  --browser.gatherUsageStats false
