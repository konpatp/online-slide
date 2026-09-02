#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

python3 tools/validate_deck.py
python3 -m unittest discover -s tests -v
python3 -m py_compile server.py slidekit.py tools/validate_deck.py tools/generate_demo_assets.py
node --check public/app.js
node --check public/recipes.js

if [[ "${ONLINE_SLIDE_BROWSER_CHECK:-0}" == "1" ]]; then
  python3 tools/browser_smoke.py
fi
