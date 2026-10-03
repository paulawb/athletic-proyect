#!/bin/sh
set -eu

python -m scripts.download_pose_model lite
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
