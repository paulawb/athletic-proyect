from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities.analysis import Analysis, AnalysisStatus


class AnalysisRepository(ABC):
    @abstractmethod
    async def create(self, analysis: Analysis) -> Analysis: ...

    @abstractmethod
    async def get_by_id(self, analysis_id: int) -> Analysis | None: ...

    @abstractmethod
    async def list(self, skip: int = 0, limit: int = 50) -> list[Analysis]: ...

    @abstractmethod
    async def list_by_video_id(self, video_id: int) -> list[Analysis]:
        """Usado para el informe (seccion 23): encontrar el analisis
        completado mas reciente de una prueba anterior del mismo atleta."""
        ...

    @abstractmethod
    async def update_progress(
        self,
        analysis_id: int,
        status: AnalysisStatus,
        processed_frames: int,
        error_message: str | None = None,
    ) -> Analysis:
        """Usado por el pipeline de procesamiento para reportar avance
        (seccion 22) y, si status=FAILED, para dejar registrado el motivo
        (seccion 16). Llamado una sola vez al terminar el recorrido o al
        fallar; para los reportes intermedios de progreso usa
        update_progress_batch (Fase 12)."""
        ...

    @abstractmethod
    async def update_progress_batch(
        self, analysis_id: int, processed_frames: int
    ) -> None:
        """Actualización ligera de progreso (solo UPDATE, sin SELECT ni
        RETURNING). Usada por ProcessVideoFrames cada N cuadros para no
        golpear la BD con un SELECT+UPDATE+RETURNING por cada 10 cuadros
        (Fase 12). El estado se mantiene PROCESSING; el cambio a
        COMPLETED/FAILED llega por update_progress al terminar."""
        ...
