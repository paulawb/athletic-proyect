"""Pruebas de carga Locust para Athletic Analysis API (Fase 12).

Cubre los endpoints críticos:
- GET /health (read-only, sin auth)
- POST /api/v1/auth/token (login JWT)
- GET /api/v1/analisis (listado con auth)
- GET /api/v1/analisis/{id} (polling de progreso)
- POST /api/v1/pruebas/{test_id}/video (upload streaming)
- POST /api/v1/analisis (enqueue analysis)
- POST /api/v1/analisis/procesar-video (endpoint combinado Fase 12)

Uso:
    locust -f locustfile.py --host=http://localhost:8000 --users 10 --spawn-rate 2 -t 60s
"""
import io

from locust import HttpUser, between, task

# Archivo de prueba: un MP4 minúsculo (container vacío, solo cabecera).
# No es un video real; sirve para medir la carga de upload + validación
# de extension/tamaño/metadatos (cv2.open) sin procesar cuadros reales.
_FAKE_MP4 = (
    b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41"
    b"\x00\x00\x00\x08free"
)
_FAKE_VIDEO = io.BytesIO(_FAKE_MP4)

# Credenciales del admin creado con scripts/create_admin.py.
# Se esperan en variables de entorno para no hardcodear secrets.
import os

ADMIN_EMAIL = os.environ.get("LOCUST_ADMIN_EMAIL", "admin@institucion.edu")
ADMIN_PASSWORD = os.environ.get("LOCUST_ADMIN_PASSWORD", "Admin123!")


class HealthUser(HttpUser):
    """Solo Golpea /health: sirve para medir la capa de FastAPI/uvicorn
    sin tocar la BD ni la lógica de negocio."""

    wait_time = between(0.1, 0.5)

    @task
    def health(self) -> None:
        self.client.get("/health")


class AnalystUser(HttpUser):
    """Simula un entrenador/administrador autenticado que consulta
    análisis, sube videos y encola procesamientos."""

    wait_time = between(1, 3)

    def on_start(self) -> None:
        self._login()

    def _login(self) -> None:
        response = self.client.post(
            "/api/v1/auth/token",
            data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        if response.status_code == 200:
            self.auth_token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.auth_token}"}
        else:
            self.auth_token = None
            self.headers = {}

    @task(3)
    def list_analyses(self) -> None:
        if not self.auth_token:
            return
        self.client.get("/api/v1/analisis", headers=self.headers)

    @task(2)
    def get_analysis(self) -> None:
        if not self.auth_token:
            return
        # Sondea un análisis existente (id=1); en producción usar un id
        # real. Si 404, no es un error de carga, es "no encontrado".
        self.client.get("/api/v1/analisis/1", headers=self.headers)

    @task(1)
    def upload_video(self) -> None:
        if not self.auth_token:
            return
        # test_id=1 debe existir en la BD de prueba; si no, el endpoint
        # responde 404 (no es un fallo de carga).
        _FAKE_VIDEO.seek(0)
        self.client.post(
            "/api/v1/pruebas/1/video",
            files={"video": ("carga_test.mp4", _FAKE_VIDEO, "video/mp4")},
            headers=self.headers,
        )

    @task(1)
    def enqueue_analysis(self) -> None:
        if not self.auth_token:
            return
        self.client.post(
            "/api/v1/analisis",
            json={"video_id": 1},
            headers=self.headers,
        )

    @task(1)
    def upload_and_queue_combined(self) -> None:
        """Endpoint combinado de la Fase 12: una sola request que sube
        el video y encola el análisis."""
        if not self.auth_token:
            return
        _FAKE_VIDEO.seek(0)
        self.client.post(
            "/api/v1/analisis/procesar-video",
            params={"test_id": 1},
            files={"video": ("carga_test.mp4", _FAKE_VIDEO, "video/mp4")},
            headers=self.headers,
        )