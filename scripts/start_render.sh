#!/bin/sh
set -eu

# Variante liviana por defecto: el plan gratuito tiene 512 MB de RAM.
python -m scripts.download_pose_model "${POSE_MODEL_VARIANT:-lite}"
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --timeout-keep-alive 30
