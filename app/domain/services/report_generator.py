from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from app.domain.entities.frame_metrics import FrameMetrics
from app.domain.entities.metrics import Metrics


@dataclass(frozen=True)
class ComparisonPoint:
    """Un punto de comparacion con una prueba anterior del mismo atleta
    (seccion 23: "comparacion con pruebas anteriores")."""

    test_label: str
    test_date: datetime | None
    average_speed: float
    cadence: float
    stride_length: float
    posture_score: float


@dataclass(frozen=True)
class AnalysisReportData:
    """Todo lo que necesita un informe de un analisis (seccion 23): atleta,
    fecha, video, metricas, datos por cuadro para graficos, y comparacion
    con pruebas anteriores del mismo atleta. GenerateAnalysisReport
    (Fase 11) la ensambla desde varios repositorios; ReportGenerator
    solo la recibe ya armada -no conoce SQLAlchemy ni ningun repositorio."""

    athlete_full_name: str
    athlete_identification: str
    test_label: str
    test_date: datetime | None
    test_distance: int
    test_type: str
    technique: str
    video_filename: str
    analysis_id: int
    metrics: Metrics
    frame_metrics: list[FrameMetrics] = field(default_factory=list)
    previous_tests: list[ComparisonPoint] = field(default_factory=list)


class ReportGenerator(ABC):
    """Puerto de inversion de dependencia (seccion 23). PdfReportGenerator
    es la primera implementacion; un ExcelReportGenerator o
    CsvReportGenerator (formatos que ya muestran las maquetas de Reportes)
    podrian agregarse despues sin tocar GenerateAnalysisReport, que solo
    conoce esta interfaz."""

    @abstractmethod
    def generate(self, report_data: AnalysisReportData) -> bytes:
        """Devuelve el documento del informe como bytes listos para
        descargar (ej. un PDF)."""
        ...
