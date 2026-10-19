from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dto.test_dto import TestCreateDTO, TestResponseDTO
from app.application.use_cases.create_test import CreateTest
from app.application.use_cases.list_tests import ListTests
from app.core.database import get_db_session
from app.core.timezone import resolve_timezone
from app.infrastructure.database.models.frame_metrics_model import FrameMetricsModel
from app.infrastructure.database.stale_analyses import fail_stale_analyses
from app.infrastructure.video.local_video_storage import LocalVideoStorage
from app.core.config import get_settings
from app.domain.entities.user import User
from app.infrastructure.database.models.analysis_model import AnalysisModel
from app.infrastructure.database.models.athlete_model import AthleteModel
from app.infrastructure.database.models.metrics_model import MetricsModel
from app.infrastructure.database.models.test_model import TestModel
from app.infrastructure.database.models.video_model import VideoModel
from app.infrastructure.database.repositories.athlete_repository_impl import SqlAlchemyAthleteRepository
from app.infrastructure.database.repositories.test_repository_impl import SqlAlchemyTestRepository
from app.presentation.api.v1.dependencies import get_current_user
from app.presentation.api.v1.ownership import get_user_timezone, require_owned_athlete, require_owned_test, user_id

router = APIRouter(prefix="/api/v1/pruebas", tags=["pruebas"])


@router.post("", response_model=TestResponseDTO, status_code=201)
async def create_test(
    data: TestCreateDTO,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> TestResponseDTO:
    await require_owned_athlete(session, data.athlete_id, user_id(current_user))
    test_repository = SqlAlchemyTestRepository(session)
    athlete_repository = SqlAlchemyAthleteRepository(session)
    tz_name = await get_user_timezone(session, user_id(current_user))
    test = await CreateTest(test_repository, athlete_repository).execute(data, tz_name)
    return TestResponseDTO.model_validate(test)


@router.get("", response_model=list[TestResponseDTO])
async def list_tests(
    athlete_id: int | None = Query(default=None, description="Filtra las pruebas de un atleta especifico"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, max_length=20),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    response_meta: Response = None,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[TestResponseDTO]:
    await fail_stale_analyses(session)
    owner_filter = TestModel.athlete_id.in_(
        select(AthleteModel.id).where(AthleteModel.owner_user_id == user_id(current_user))
    )
    latest_analysis_id = (
        select(AnalysisModel.id)
        .join(VideoModel, VideoModel.id == AnalysisModel.video_id)
        .where(VideoModel.test_id == TestModel.id)
        .order_by(AnalysisModel.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    latest_status = (
        select(AnalysisModel.status)
        .where(AnalysisModel.id == latest_analysis_id)
        .scalar_subquery()
        .label("analysis_status")
    )
    conditions = [owner_filter]
    if athlete_id is not None:
        conditions.append(TestModel.athlete_id == athlete_id)
    if q:
        term = f"%{q.strip()}%"
        conditions.append(
            or_(
                func.cast(TestModel.id, str).ilike(term),
                AthleteModel.first_name.ilike(term),
                AthleteModel.last_name.ilike(term),
                TestModel.test_type.ilike(term),
                TestModel.technique.ilike(term),
            )
        )
    if status:
        conditions.append(func.upper(func.coalesce(latest_status, TestModel.status)) == status.upper())
    zone = resolve_timezone(await get_user_timezone(session, user_id(current_user)))
    if date_from:
        conditions.append(TestModel.created_at >= datetime.combine(date_from, time.min, tzinfo=zone))
    if date_to:
        conditions.append(
            TestModel.created_at < datetime.combine(
                date.fromordinal(date_to.toordinal() + 1), time.min, tzinfo=zone
            )
        )

    query = (
        select(TestModel, latest_status, MetricsModel)
        .join(AthleteModel, AthleteModel.id == TestModel.athlete_id)
        .outerjoin(MetricsModel, MetricsModel.analysis_id == latest_analysis_id)
    )
    count_query = select(func.count()).select_from(TestModel).join(
        AthleteModel, AthleteModel.id == TestModel.athlete_id
    )
    if conditions:
        query = query.where(*conditions)
        count_query = count_query.where(*conditions)
    rows = (
        await session.execute(query.order_by(TestModel.created_at.desc()).offset(skip).limit(limit))
    ).all()
    response = []
    for test, analysis_state, metrics in rows:
        result = TestResponseDTO.model_validate(test)
        result.analysis_status = analysis_state
        if metrics:
            result.average_speed = metrics.average_speed
            result.maximum_speed = metrics.maximum_speed
            result.stride_length = metrics.stride_length
            result.cadence = metrics.cadence
            result.posture_score = metrics.posture_score
        response.append(result)
    if response_meta is not None:
        response_meta.headers["X-Total-Count"] = str(await session.scalar(count_query) or 0)
    return response


@router.delete("/{test_id}", status_code=204)
async def delete_test(
    test_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Borra la prueba con sus videos, analisis, metricas y archivos."""
    test = await require_owned_test(session, test_id, user_id(current_user))
    videos = (await session.execute(select(VideoModel).where(VideoModel.test_id == test.id))).scalars().all()
    video_ids = [video.id for video in videos]
    storage_paths = [video.storage_path for video in videos]
    if video_ids:
        analysis_ids = select(AnalysisModel.id).where(AnalysisModel.video_id.in_(video_ids))
        await session.execute(delete(FrameMetricsModel).where(FrameMetricsModel.analysis_id.in_(analysis_ids)))
        await session.execute(delete(MetricsModel).where(MetricsModel.analysis_id.in_(analysis_ids)))
        await session.execute(delete(AnalysisModel).where(AnalysisModel.video_id.in_(video_ids)))
        await session.execute(delete(VideoModel).where(VideoModel.id.in_(video_ids)))
    await session.delete(test)
    await session.commit()
    storage = LocalVideoStorage(get_settings().storage_local_path)
    for path in storage_paths:
        try:
            await storage.delete(path)
        except OSError:
            pass
    return Response(status_code=204)


@router.get("/summary")
async def get_test_summary(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, int]:
    await fail_stale_analyses(session)
    owner_id = user_id(current_user)
    owned_tests = select(TestModel.id).join(
        AthleteModel, AthleteModel.id == TestModel.athlete_id
    ).where(AthleteModel.owner_user_id == owner_id)
    total = await session.scalar(select(func.count()).select_from(TestModel).where(TestModel.id.in_(owned_tests))) or 0
    zone = resolve_timezone(await get_user_timezone(session, owner_id))
    start_of_month = datetime.now(zone).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    this_month = await session.scalar(
        select(func.count()).select_from(TestModel).where(
            TestModel.id.in_(owned_tests), TestModel.created_at >= start_of_month
        )
    ) or 0
    completed = await session.scalar(
        select(func.count(func.distinct(TestModel.id)))
        .select_from(TestModel)
        .join(VideoModel, VideoModel.test_id == TestModel.id)
        .join(AnalysisModel, AnalysisModel.video_id == VideoModel.id)
        .join(AthleteModel, AthleteModel.id == TestModel.athlete_id)
        .where(AthleteModel.owner_user_id == owner_id, func.upper(AnalysisModel.status) == "COMPLETED")
    ) or 0
    processing = await session.scalar(
        select(func.count(func.distinct(TestModel.id)))
        .select_from(TestModel)
        .join(VideoModel, VideoModel.test_id == TestModel.id)
        .join(AnalysisModel, AnalysisModel.video_id == VideoModel.id)
        .join(AthleteModel, AthleteModel.id == TestModel.athlete_id)
        .where(AthleteModel.owner_user_id == owner_id, func.upper(AnalysisModel.status).in_(("PENDING", "PROCESSING")))
    ) or 0
    return {"total": total, "this_month": this_month, "completed": completed, "processing": processing}
