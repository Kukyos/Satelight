@echo off
rem OceanEmbed PoC: build the viewer if needed, serve it with the API, open the browser.
cd /d "%~dp0"
if not exist viewer\dist\index.html (
  pushd viewer && call npm install && call npx vite build && popd
)
start "" http://127.0.0.1:8026/
.venv\Scripts\python.exe -m uvicorn oceanembed.api:app --host 127.0.0.1 --port 8026
