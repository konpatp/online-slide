#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

python3 tools/validate_deck.py
python3 -m unittest discover -s tests -v
python3 -m py_compile server.py slidekit.py build_deck.py tools/validate_deck.py tools/generate_demo_assets.py
node --check public/app.js
node --check public/slide-previews.js
node --check public/recipes.js
node --check public/catalog.js
node --check public/joint-diagram.js
node --check public/chart-panels.js

if [[ "${ONLINE_SLIDE_BROWSER_CHECK:-0}" == "1" ]]; then
  python3 tools/browser_smoke.py
  python3 tools/browser_concurrency.py
  python3 tools/browser_transport.py
  python3 tools/browser_wysiwyg.py
fi
