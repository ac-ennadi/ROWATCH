#!/usr/bin/env sh
set -e
cd "$(dirname "$0")/backend"
if [ ! -d .venv ]; then
  python -m venv .venv
fi
. .venv/bin/activate
pip install -r requirements.txt
python app.py
