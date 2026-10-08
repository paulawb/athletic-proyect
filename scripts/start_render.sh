#!/bin/sh
set -eu

python -m scripts.download_pose_model full
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
