from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuracion centralizada de la aplicacion, cargada desde variables
    de entorno o un archivo .env. Nunca contiene secretos hardcodeados."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    environment: str = "development"

    database_url: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    max_video_size_mb: int = 500

    storage_backend: str = "local"
    storage_local_path: str = "./storage"

    # Fase 9: "mediapipe" (deteccion real) o "mock" (solo pruebas visuales)
    # (modelo real). Cambiar esto no requiere tocar codigo en ningun caso de
    # uso -PoseEstimator es una interfaz de dominio; ver seccion 9.
    pose_estimator_backend: str = "mediapipe"
    mediapipe_model_path: str = "models/pose_landmarker_full.task"
    mediapipe_min_detection_confidence: float = 0.5
    mediapipe_min_presence_confidence: float = 0.65
    mediapipe_min_tracking_confidence: float = 0.5

    # Fase 10: "basic" (Fase 6, heuristicas simples) o "biomechanical"
    # (angulo real de inclinacion del tronco, deteccion de apoyos por
    # velocidad). "linear" (escala simple, Fase 6) o "homography"
    # (correccion de perspectiva real, Fase 10) para la calibracion.
    # Ninguno de los dos requiere tocar ProcessVideoFrames al cambiarlos.
    metrics_calculator_backend: str = "basic"
    calibration_backend: str = "linear"
    track_lane_width_m: float = 1.22

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    log_level: str = "INFO"

    @field_validator("database_url", mode="before")
    @classmethod
    def use_async_postgres_driver(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
