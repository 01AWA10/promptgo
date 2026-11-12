#!/usr/bin/env sh
# PromptGo 本地服务启动脚本（macOS / Linux）
set -e
PORT="${1:-7317}"
DIR="$(cd "$(dirname "$0")" && pwd)"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "[错误] 未检测到 Python 3，请先安装 Python 3.11+。" >&2
  exit 1
fi

exec "$PY" "$DIR/server/app.py" --port "$PORT" --open
