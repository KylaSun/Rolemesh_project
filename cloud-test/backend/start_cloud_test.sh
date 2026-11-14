#!/bin/sh
set -eu
if [ "${ROLEMESH_ENV:-}" != "test" ]; then
    echo 'Set ROLEMESH_ENV=test for this test-only service.' >&2
    exit 1
fi
python database.py
python seed_demo.py
python seed_projects.py
exec python -m uvicorn main:app --host 0.0.0.0 --port 8000
