#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PY=""
if [[ -x .venv/bin/python ]] && .venv/bin/python -c "import fastapi,uvicorn,httpx,PIL" 2>/dev/null; then
  PY=".venv/bin/python"
elif python3 -c "import fastapi,uvicorn,httpx,PIL" 2>/dev/null; then
  PY="python3"
else
  if [[ ! -x .venv/bin/python ]]; then
    if python3 -m venv .venv 2>/dev/null; then
      :
    elif command -v virtualenv >/dev/null; then
      virtualenv .venv
    else
      echo "缺少 fastapi、uvicorn、httpx、pillow，且无法创建虚拟环境。可安装 python3-venv 后重试。" >&2
      exit 1
    fi
  fi
  .venv/bin/pip install -r requirements.txt
  PY=".venv/bin/python"
fi

exec "$PY" -m uvicorn server.main:app --host 0.0.0.0 --port 8080
