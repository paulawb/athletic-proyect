from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dto.video_dto import VideoResponseDTO
from app.application.use_cases.get_test_video import GetTestVideo
from app.application.use_cases.get_video import GetVideo
from app.application.use_cases.upload_video import UploadVideo
from app.core.config import get_settings
from app.core.database import get_db_session
from app.domain.entities.user import User
from app.infrastructure.database.repositories.test_repository_impl import SqlAlchemyTestRepository
from app.infrastructure.database.repositories.video_repository_impl import SqlAlchemyVideoRepository
from app.infrastructure.video.local_video_storage import LocalVideoStorage
from app.infrastructure.video.opencv_frame_processor import OpenCVFrameProcessor
from app.presentation.api.v1.dependencies import get_current_user
from app.presentation.api.v1.ownership import require_owned_test, require_owned_video, user_id

router = APIRouter(prefix="/api/v1", tags=["videos"])


def _build_upload_use_case(session: AsyncSession) -> UploadVideo:
    settings = get_settings()
    return UploadVideo(
        test_repository=SqlAlchemyTestRepository(session),
        video_repository=SqlAlchemyVideoRepository(session),
        video_storage=LocalVideoStorage(settings.storage_local_path),
        frame_processor=OpenCVFrameProcessor(),
        max_size_bytes=settings.max_video_size_mb * 1024 * 1024,
    )


@router.post("/pruebas/{test_id}/video", response_model=VideoResponseDTO, status_code=201)
async def upload_test_video(
    test_id: int,
    video: UploadFile = File(..., description="Archivo de video (MP4 o MOV)"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> VideoResponseDTO:
    await require_owned_test(session, test_id, user_id(current_user))
    use_case = _build_upload_use_case(session)
    result = await use_case.execute(test_id, video)
    return VideoResponseDTO.model_validate(result)


@router.get("/pruebas/{test_id}/video", response_model=VideoResponseDTO)
async def get_test_video(
    test_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> VideoResponseDTO:
    await require_owned_test(session, test_id, user_id(current_user))
    repository = SqlAlchemyVideoRepository(session)
    video = await GetTestVideo(repository).execute(test_id)
    return VideoResponseDTO.model_validate(video)


@router.get("/videos/{video_id}", response_model=VideoResponseDTO)
async def get_video(
    video_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> VideoResponseDTO:
    await require_owned_video(session, video_id, user_id(current_user))
    repository = SqlAlchemyVideoRepository(session)
    video = await GetVideo(repository).execute(video_id)
    return VideoResponseDTO.model_validate(video)


@router.get("/videos/{video_id}/content")
async def get_video_content(
    video_id: int,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    video = await require_owned_video(session, video_id, user_id(current_user))
    path = Path(LocalVideoStorage(get_settings().storage_local_path).get_absolute_path(video.storage_path))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="El archivo del video no está disponible")
    content_type = "video/quicktime" if path.suffix.lower() == ".mov" else "video/mp4"
    return FileResponse(path, media_type=content_type, filename=video.original_filename)
