#!/bin/sh
set -eu

if [ "${ROLEMESH_ENV:-}" != "rolemesh-test" ]; then
    echo "Refusing to load fictional fixtures outside rolemesh-test." >&2
    exit 1
fi

python database.py
python seed_demo.py
python seed_projects.py

exec python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
