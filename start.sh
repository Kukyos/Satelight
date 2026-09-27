#!/usr/bin/env sh
# OceanEmbed PoC: build the viewer if needed, serve it with the API, open the browser.
cd "$(dirname "$0")"
if [ ! -f viewer/dist/index.html ]; then
  (cd viewer && npm install && npx vite build)
fi
PY=.venv/bin/python
[ -x "$PY" ] || PY=.venv/Scripts/python.exe
( sleep 2; (xdg-open http://127.0.0.1:8026/ || open http://127.0.0.1:8026/) >/dev/null 2>&1 ) &
exec "$PY" -m uvicorn oceanembed.api:app --host 127.0.0.1 --port 8026
