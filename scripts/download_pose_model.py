"""Descarga el modelo Pose Landmarker de MediaPipe (Fase 9).

Uso:
    python -m scripts.download_pose_model [lite|full|heavy]

Por defecto descarga "lite" (~5-9 MB, el mas liviano/rapido). "full" y
"heavy" son mas precisos pero mas lentos -ver la guia oficial de MediaPipe
para el tradeoff exacto. El archivo queda en la ruta de
MEDIAPIPE_MODEL_PATH (por defecto models/pose_landmarker_lite.task).

Requiere conexion a internet: descarga desde storage.googleapis.com.
"""
import sys
import urllib.request
from pathlib import Path

from app.core.config import get_settings

_MODEL_URLS = {
    "lite": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
    "full": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task",
    "heavy": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task",
}


def main(variant: str) -> None:
    if variant not in _MODEL_URLS:
        print(f"Variante desconocida '{variant}'. Opciones: {', '.join(_MODEL_URLS)}")
        sys.exit(1)

    settings = get_settings()
    destination = Path(settings.mediapipe_model_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        print(f"Ya existe {destination}; no se vuelve a descargar (borralo si quieres forzarlo).")
        return

    url = _MODEL_URLS[variant]
    print(f"Descargando {url} -> {destination} ...")
    urllib.request.urlretrieve(url, destination)
    print("Listo.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "lite")
