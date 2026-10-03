from datetime import datetime, timezone

from app.core.exceptions import AnalysisNotFoundError, MetricsNotFoundError
from app.domain.entities.analysis import AnalysisStatus
from app.domain.repositories.analysis_repository import AnalysisRepository
from app.domain.repositories.athlete_repository import AthleteRepository
from app.domain.repositories.metrics_repository import FrameMetricsRepository, MetricsRepository
from app.domain.repositories.test_repository import TestRepository
from app.domain.repositories.video_repository import VideoRepository
from app.domain.services.report_generator import AnalysisReportData, ComparisonPoint, ReportGenerator


class GenerateAnalysisReport:
    """Caso de uso de la Fase 11 (seccion 23): reune atleta, prueba, video,
    metricas, el detalle por cuadro (para graficos) y una comparacion con
    pruebas anteriores del mismo atleta, y le pide a ReportGenerator que
    arme el documento. No sabe nada de PDF/Excel/reportlab -eso es
    responsabilidad de la implementacion concreta que reciba."""

    def __init__(
        self,
        analysis_repository: AnalysisRepository,
        video_repository: VideoRepository,
        test_repository: TestRepository,
        athlete_repository: AthleteRepository,
        metrics_repository: MetricsRepository,
        frame_metrics_repository: FrameMetricsRepository,
        report_generator: ReportGenerator,
    ) -> None:
        self._analysis_repository = analysis_repository
        self._video_repository = video_repository
        self._test_repository = test_repository
        self._athlete_repository = athlete_repository
        self._metrics_repository = metrics_repository
        self._frame_metrics_repository = frame_metrics_repository
        self._report_generator = report_generator

    async def execute(self, analysis_id: int) -> bytes:
        analysis = await self._analysis_repository.get_by_id(analysis_id)
        if analysis is None:
            raise AnalysisNotFoundError(f"No existe un analisis con id={analysis_id}")

        metrics = await self._metrics_repository.get_by_analysis_id(analysis_id)
        if metrics is None:
            raise MetricsNotFoundError(
                f"El analisis id={analysis_id} todavia no tiene metricas "
                f"(estado actual: {analysis.status.value})"
            )

        video = await self._video_repository.get_by_id(analysis.video_id)
        test = await self._test_repository.get_by_id(video.test_id) if video else None
        athlete = await self._athlete_repository.get_by_id(test.athlete_id) if test else None

        frame_metrics = await self._frame_metrics_repository.list_by_analysis_id(analysis_id)

        previous_tests = (
            await self._build_comparison(athlete_id=test.athlete_id, exclude_test_id=test.id)
            if test is not None
            else []
        )

        report_data = AnalysisReportData(
            athlete_full_name=(
                f"{athlete.first_name} {athlete.last_name}" if athlete is not None else "Atleta desconocido"
            ),
            athlete_identification=athlete.identification if athlete is not None else "-",
            test_label=f"Prueba #{test.id}" if test is not None else "-",
            test_date=test.created_at if test is not None else None,
            test_distance=test.distance if test is not None else 0,
            test_type=test.test_type if test is not None else "-",
            technique=test.technique if test is not None else "-",
            video_filename=video.original_filename if video is not None else "-",
            analysis_id=analysis_id,
            metrics=metrics,
            frame_metrics=frame_metrics,
            previous_tests=previous_tests,
        )

        return self._report_generator.generate(report_data)

    async def _build_comparison(self, athlete_id: int, exclude_test_id: int) -> list[ComparisonPoint]:
        """Para cada prueba anterior del atleta (excluyendo la actual), toma
        el analisis completado mas reciente de su video y sus metricas.
        Pruebas sin video, sin analisis completado, o sin metricas
        simplemente no aportan un punto de comparacion -no es un error,
        es normal que una prueba anterior siga en proceso o haya fallado."""
        comparison: list[ComparisonPoint] = []

        tests = await self._test_repository.list_by_athlete(athlete_id)
        for other_test in tests:
            if other_test.id == exclude_test_id:
                continue

            other_video = await self._video_repository.get_by_test_id(other_test.id)
            if other_video is None:
                continue

            other_analyses = await self._analysis_repository.list_by_video_id(other_video.id)
            completed = [a for a in other_analyses if a.status == AnalysisStatus.COMPLETED and a.completed_at]
            if not completed:
                continue
            latest = max(completed, key=lambda a: a.completed_at)

            other_metrics = await self._metrics_repository.get_by_analysis_id(latest.id)
            if other_metrics is None:
                continue

            comparison.append(
                ComparisonPoint(
                    test_label=f"Prueba #{other_test.id}",
                    test_date=other_test.created_at,
                    average_speed=other_metrics.average_speed,
                    cadence=other_metrics.cadence,
                    stride_length=other_metrics.stride_length,
                    posture_score=other_metrics.posture_score,
                )
            )

        # Clave de orden que nunca mezcla tipos: si test_date es None, ese
        # punto queda al final (True > False), sin comparar datetime con str.
        comparison.sort(
            key=lambda point: (point.test_date is None, point.test_date or datetime.min.replace(tzinfo=timezone.utc))
        )
        return comparison
