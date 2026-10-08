from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.user import User
from app.infrastructure.database.models.analysis_model import AnalysisModel
from app.infrastructure.database.models.athlete_model import AthleteModel
from app.infrastructure.database.models.test_model import TestModel
from app.infrastructure.database.models.video_model import VideoModel


def user_id(current_user: User) -> int:
    if current_user.id is None:
        raise HTTPException(status_code=401, detail="Usuario no autenticado")
    return current_user.id


def owned_analysis_query(owner_id: int):
    return (
        select(AnalysisModel)
        .join(VideoModel, VideoModel.id == AnalysisModel.video_id)
        .join(TestModel, TestModel.id == VideoModel.test_id)
        .join(AthleteModel, AthleteModel.id == TestModel.athlete_id)
        .where(AthleteModel.owner_user_id == owner_id)
    )


async def require_owned_athlete(
    session: AsyncSession, athlete_id: int, owner_id: int
) -> AthleteModel:
    athlete = await session.scalar(
        select(AthleteModel).where(
            AthleteModel.id == athlete_id,
            AthleteModel.owner_user_id == owner_id,
        )
    )
    if athlete is None:
        raise HTTPException(status_code=404, detail="Atleta no encontrado")
    return athlete


async def require_owned_test(session: AsyncSession, test_id: int, owner_id: int) -> TestModel:
    test = await session.scalar(
        select(TestModel)
        .join(AthleteModel, AthleteModel.id == TestModel.athlete_id)
        .where(TestModel.id == test_id, AthleteModel.owner_user_id == owner_id)
    )
    if test is None:
        raise HTTPException(status_code=404, detail="Prueba no encontrada")
    return test


async def require_owned_analysis(
    session: AsyncSession, analysis_id: int, owner_id: int
) -> AnalysisModel:
    analysis = await session.scalar(
        owned_analysis_query(owner_id).where(AnalysisModel.id == analysis_id)
    )
    if analysis is None:
        raise HTTPException(status_code=404, detail="Análisis no encontrado")
    return analysis


async def require_owned_video(session: AsyncSession, video_id: int, owner_id: int) -> VideoModel:
    video = await session.scalar(
        select(VideoModel)
        .join(TestModel, TestModel.id == VideoModel.test_id)
        .join(AthleteModel, AthleteModel.id == TestModel.athlete_id)
        .where(VideoModel.id == video_id, AthleteModel.owner_user_id == owner_id)
    )
    if video is None:
        raise HTTPException(status_code=404, detail="Video no encontrado")
    return video
