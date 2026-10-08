from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dto.analysis_dto import (
    AnalysisCreateDTO,
    AnalysisCreatedResponseDTO,
    AnalysisMetricsResponseDTO,
    AnalysisResponseDTO,
)
from app.application.ports.task_runner import TaskRunner
from app.application.use_cases.create_analysis import CreateAnalysis
from app.application.use_cases.generate_analysis_report import GenerateAnalysisReport
from app.application.use_cases.get_analysis import GetAnalysis
from app.application.use_cases.get_analysis_metrics import GetAnalysisMetrics
from app.application.use_cases.process_video_frames import CalibratorFactory, ProcessVideoFrames
from app.application.use_cases.upload_video import UploadVideo
from app.domain.dto.process_video_dto import ProcessVideoResponseDTO
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.domain.entities.user import User
from app.domain.entities.video import Video
from app.domain.services.metrics_calculator import CameraCalibration, CoordinateCalibrator, MetricsCalculator
from app.domain.services.pose_estimator import PoseEstimator
from app.infrastructure.calibration.homography_coordinate_calibrator import HomographyCoordinateCalibrator
from app.infrastructure.calibration.linear_coordinate_calibrator import LinearCoordinateCalibrator
from app.infrastructure.database.repositories.analysis_repository_impl import SqlAlchemyAnalysisRepository
from app.infrastructure.database.repositories.athlete_repository_impl import SqlAlchemyAthleteRepository
from app.infrastructure.database.repositories.frame_metrics_repository_impl import (
    SqlAlchemyFrameMetricsRepository,
)
from app.infrastructure.database.repositories.metrics_repository_impl import SqlAlchemyMetricsRepository
from app.infrastructure.database.repositories.test_repository_impl import SqlAlchemyTestRepository
from app.infrastructure.database.repositories.video_repository_impl import SqlAlchemyVideoRepository
from app.infrastructure.database.models.analysis_model import AnalysisModel
from app.infrastructure.database.models.frame_metrics_model import FrameMetricsModel
from app.infrastructure.database.models.metrics_model import MetricsModel
from app.infrastructure.database.models.video_model import VideoModel
from app.infrastructure.metrics.basic_metrics_calculator import BasicMetricsCalculator
from app.infrastructure.metrics.biomechanical_metrics_calculator import BiomechanicalMetricsCalculator
from app.infrastructure.reports.pdf_report_generator import PdfReportGenerator
from app.infrastructure.tasks.background_tasks_runner import BackgroundTasksRunner
from app.infrastructure.video.local_video_storage import LocalVideoStorage
from app.infrastructure.video.opencv_frame_processor import OpenCVFrameProcessor
from app.infrastructure.vision.mediapipe_pose_estimator import MediaPipePoseEstimator
from app.infrastructure.vision.mock_pose_estimator import MockPoseEstimator
from app.presentation.api.v1.dependencies import get_current_user
from app.presentation.api.v1.ownership import (
    owned_analysis_query,
    require_owned_analysis,
    require_owned_test,
    require_owned_video,
    user_id,
)

router = APIRouter(prefix="/api/v1/analisis", tags=["analisis"])


def _build_pose_estimator(settings: Settings) -> PoseEstimator:
    """Fase 9: POSE_ESTIMATOR_BACKEND decide la implementacion sin tocar
    ningun caso de uso -ambas hablan la interfaz PoseEstimator (seccion 9).
    "mediapipe" (por defecto) usa el modelo real; "mock" solo sirve para
    pruebas visuales y no detecta personas (ver scripts/download_pose_model.py)."""
    if settings.pose_estimator_backend == "mediapipe":
        return MediaPipePoseEstimator(
            model_path=settings.mediapipe_model_path,
            min_detection_confidence=settings.mediapipe_min_detection_confidence,
            min_presence_confidence=settings.mediapipe_min_presence_confidence,
            min_tracking_confidence=settings.mediapipe_min_tracking_confidence,
        )
    return MockPoseEstimator()


def _build_metrics_calculator(settings: Settings) -> MetricsCalculator:
    """Fase 10: METRICS_CALCULATOR_BACKEND elige entre las heuristicas
    simples de la Fase 6 y las formulas biomecanicas de la Fase 10, sin
    tocar ProcessVideoFrames -ambas hablan la interfaz MetricsCalculator."""
    if settings.metrics_calculator_backend == "biomechanical":
        return BiomechanicalMetricsCalculator()
    return BasicMetricsCalculator()


def _build_calibrator_factory(settings: Settings) -> CalibratorFactory:
    """Fase 10: arma la fabrica de CoordinateCalibrator que ProcessVideoFrames
    necesita (ver CalibratorFactory: depende del video/prueba, no se puede
    construir una sola vez). CALIBRATION_BACKEND elige entre la escala
    lineal simple (Fase 6) y la homografia con correccion de perspectiva
    (Fase 10); en ambos casos, sin puntos de referencia reales de la toma
    todavia, se usa el cuadro completo como aproximacion (ver
    HomographyCoordinateCalibrator.from_frame_corners)."""

    def factory(video: Video, reference_distance_m: float) -> CoordinateCalibrator:
        if not video.width or not video.height:
            raise ValueError("dimensiones del video desconocidas")

        if settings.calibration_backend == "homography":
            return HomographyCoordinateCalibrator.from_frame_corners(
                frame_width_px=video.width,
                frame_height_px=video.height,
                reference_distance_m=reference_distance_m,
                lane_width_m=settings.track_lane_width_m,
            )

        pixels_per_meter = video.width / reference_distance_m
        return LinearCoordinateCalibrator(
            CameraCalibration(pixels_per_meter=pixels_per_meter, reference_distance_m=reference_distance_m)
        )

    return factory


def _build_process_video_frames_use_case(session: AsyncSession) -> ProcessVideoFrames:
    settings = get_settings()
    return ProcessVideoFrames(
        video_repository=SqlAlchemyVideoRepository(session),
        test_repository=SqlAlchemyTestRepository(session),
        analysis_repository=SqlAlchemyAnalysisRepository(session),
        metrics_repository=SqlAlchemyMetricsRepository(session),
        frame_metrics_repository=SqlAlchemyFrameMetricsRepository(session),
        video_storage=LocalVideoStorage(settings.storage_local_path),
        frame_processor=OpenCVFrameProcessor(),
        pose_estimator=_build_pose_estimator(settings),
        metrics_calculator=_build_metrics_calculator(settings),
        calibrator_factory=_build_calibrator_factory(settings),
    )


@router.post("", response_model=AnalysisCreatedResponseDTO, status_code=202)
async def create_analysis(
    data: AnalysisCreateDTO,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> AnalysisCreatedResponseDTO:
    """Fase 8 (secciones 12-13): crea el Analysis en PENDING y encola el
    procesamiento real; responde de inmediato sin esperar a que termine.

    La sesion de base de datos sigue viva durante la tarea en segundo
    plano: FastAPI cierra las dependencias con "yield" (como get_db_session)
    despues de que las BackgroundTasks terminan, no antes, precisamente
    para permitir este patron.
    """
    await require_owned_video(session, data.video_id, user_id(current_user))
    analysis = await CreateAnalysis(
        video_repository=SqlAlchemyVideoRepository(session),
        analysis_repository=SqlAlchemyAnalysisRepository(session),
    ).execute(data.video_id)

    async def _run_processing() -> None:
        use_case = _build_process_video_frames_use_case(session)
        await use_case.execute(analysis.id, data.video_id)

    task_runner: TaskRunner = BackgroundTasksRunner(background_tasks)
    task_runner.enqueue(_run_processing)

    return AnalysisCreatedResponseDTO(
        analysis_id=analysis.id, status=analysis.status, message="Video en cola para procesamiento"
    )


@router.get("", response_model=list[AnalysisResponseDTO])
async def list_analyses(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[AnalysisResponseDTO]:
    repository = SqlAlchemyAnalysisRepository(session)
    analysis_models = (
        await session.execute(
            owned_analysis_query(user_id(current_user))
            .order_by(AnalysisModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
    ).scalars().all()
    analyses = [
        analysis
        for model in analysis_models
        if (analysis := await repository.get_by_id(model.id)) is not None
    ]
    return [AnalysisResponseDTO.model_validate(a) for a in analyses]


@router.get("/{analysis_id}", response_model=AnalysisResponseDTO)
async def get_analysis(
    analysis_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> AnalysisResponseDTO:
    """Fase 8: este es el endpoint que el frontend debe sondear (polling)
    para ver como avanza processed_frames/progress_percentage hasta que
    status pase a COMPLETED o FAILED."""
    await require_owned_analysis(session, analysis_id, user_id(current_user))
    repository = SqlAlchemyAnalysisRepository(session)
    analysis = await GetAnalysis(repository).execute(analysis_id)
    return AnalysisResponseDTO.model_validate(analysis)


@router.get("/{analysis_id}/metricas", response_model=AnalysisMetricsResponseDTO)
async def get_analysis_metrics(
    analysis_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> AnalysisMetricsResponseDTO:
    """Fase 7: las metricas ya persistidas (seccion 14-15). 404 si el
    analisis no existe, o si existe pero todavia no tiene metricas (por
    ejemplo, sigue en PENDING/PROCESSING, o termino en FAILED)."""
    await require_owned_analysis(session, analysis_id, user_id(current_user))
    analysis_repository = SqlAlchemyAnalysisRepository(session)
    metrics_repository = SqlAlchemyMetricsRepository(session)
    metrics = await GetAnalysisMetrics(analysis_repository, metrics_repository).execute(analysis_id)
    return AnalysisMetricsResponseDTO.model_validate(metrics)


@router.get("/{analysis_id}/frames")
async def get_analysis_frames(
    analysis_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    analysis = await require_owned_analysis(session, analysis_id, user_id(current_user))
    video = await session.get(VideoModel, analysis.video_id)
    frames = (
        await session.execute(
            select(FrameMetricsModel)
            .where(FrameMetricsModel.analysis_id == analysis_id)
            .order_by(FrameMetricsModel.frame_number)
        )
    ).scalars().all()
    return {
        "analysis_id": analysis_id,
        "video_id": video.id if video else None,
        "width": video.width if video else None,
        "height": video.height if video else None,
        "duration": video.duration if video else None,
        "frames": [
            {
                "frame_number": frame.frame_number,
                "timestamp": frame.timestamp,
                "x_position": frame.x_position,
                "y_position": frame.y_position,
                "speed": frame.speed,
                "stride_phase": frame.stride_phase,
                "posture_score": frame.posture_score,
                "keypoints": frame.keypoints or [],
            }
            for frame in frames
        ],
    }


@router.get("/{analysis_id}/compare/{other_analysis_id}")
async def compare_analyses(
    analysis_id: int,
    other_analysis_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    owner_id = user_id(current_user)
    await require_owned_analysis(session, analysis_id, owner_id)
    await require_owned_analysis(session, other_analysis_id, owner_id)
    first = await session.scalar(select(MetricsModel).where(MetricsModel.analysis_id == analysis_id))
    second = await session.scalar(
        select(MetricsModel).where(MetricsModel.analysis_id == other_analysis_id)
    )
    if first is None or second is None:
        raise HTTPException(status_code=404, detail="Uno de los análisis no tiene resultados disponibles")
    fields = ("average_speed", "maximum_speed", "stride_length", "cadence", "posture_score")
    return {
        "analysis_id": analysis_id,
        "other_analysis_id": other_analysis_id,
        "metrics": {
            field: {
                "current": getattr(first, field),
                "comparison": getattr(second, field),
                "difference": round(getattr(first, field) - getattr(second, field), 3),
            }
            for field in fields
        },
    }


@router.get("/{analysis_id}/reporte")
async def get_analysis_report(
    analysis_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Fase 11 (seccion 23): informe en PDF del analisis -atleta, prueba,
    metricas, grafico de velocidad, y comparacion con pruebas anteriores
    del mismo atleta si las hay. 404 si el analisis no existe o todavia no
    tiene metricas (mismo criterio que /metricas)."""
    await require_owned_analysis(session, analysis_id, user_id(current_user))
    use_case = GenerateAnalysisReport(
        analysis_repository=SqlAlchemyAnalysisRepository(session),
        video_repository=SqlAlchemyVideoRepository(session),
        test_repository=SqlAlchemyTestRepository(session),
        athlete_repository=SqlAlchemyAthleteRepository(session),
        metrics_repository=SqlAlchemyMetricsRepository(session),
        frame_metrics_repository=SqlAlchemyFrameMetricsRepository(session),
        report_generator=PdfReportGenerator(),
    )
    pdf_bytes = await use_case.execute(analysis_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="informe-analisis-{analysis_id}.pdf"'},
    )


@router.post("/procesar-video", response_model=ProcessVideoResponseDTO, status_code=202)
async def upload_and_queue_analysis(
    test_id: int,
    video: UploadFile = File(..., description="Archivo de video (MP4 o MOV)"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ProcessVideoResponseDTO:
    """Fase 12: endpoint combinado. Sube el video, crea el Analysis en
    PENDING y encola el procesamiento en una sola llamada. Equivale a
    POST /api/v1/pruebas/{test_id}/video seguido de
    POST /api/v1/analisis, pero con una sola request HTTP y una sola
    transaccion de base de datos para la escritura del archivo.

    La sesion de BD sigue viva mientras la tarea en segundo plano
    procesa el video, exactamente igual que en create_analysis.
    """
    await require_owned_test(session, test_id, user_id(current_user))
    settings = get_settings()
    upload_use_case = UploadVideo(
        test_repository=SqlAlchemyTestRepository(session),
        video_repository=SqlAlchemyVideoRepository(session),
        video_storage=LocalVideoStorage(settings.storage_local_path),
        frame_processor=OpenCVFrameProcessor(),
        max_size_bytes=settings.max_video_size_mb * 1024 * 1024,
    )
    stored = await upload_use_case.execute(test_id, video)
    if stored.id is None:
        raise HTTPException(status_code=500, detail="No se pudo registrar el video cargado")

    analysis = await CreateAnalysis(
        video_repository=SqlAlchemyVideoRepository(session),
        analysis_repository=SqlAlchemyAnalysisRepository(session),
    ).execute(stored.id)

    async def _run_processing() -> None:
        use_case = _build_process_video_frames_use_case(session)
        await use_case.execute(analysis.id, analysis.video_id)

    task_runner: TaskRunner = BackgroundTasksRunner(background_tasks)
    task_runner.enqueue(_run_processing)

    return ProcessVideoResponseDTO(
        video_id=analysis.video_id,
        analysis_id=analysis.id,
        status=analysis.status,
    )
