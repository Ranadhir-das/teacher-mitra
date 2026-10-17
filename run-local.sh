#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
else
    echo "Python not found. Please setup virtual environment first." >&2
    exit 1
fi

export DEBUG="True"
echo "Starting TeacherMitra development server at http://127.0.0.1:8000/ ..."
exec "$PYTHON" manage.py runserver 127.0.0.1:8000
