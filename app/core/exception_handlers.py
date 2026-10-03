from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    AnalysisNotFoundError,
    AthleteNotFoundError,
    InvalidCredentialsError,
    InvalidVideoFormatError,
    MetricsNotFoundError,
    TestNotFoundError,
    VideoNotFoundError,
    VideoProcessingError,
    VideoTooLargeError,
)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(InvalidVideoFormatError)
    async def invalid_video_format_handler(request: Request, exc: InvalidVideoFormatError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})

    @app.exception_handler(VideoTooLargeError)
    async def video_too_large_handler(request: Request, exc: VideoTooLargeError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, content={"detail": str(exc)})

    @app.exception_handler(VideoProcessingError)
    async def video_processing_handler(request: Request, exc: VideoProcessingError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": str(exc)})

    @app.exception_handler(AnalysisNotFoundError)
    async def analysis_not_found_handler(request: Request, exc: AnalysisNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})

    @app.exception_handler(AthleteNotFoundError)
    async def athlete_not_found_handler(request: Request, exc: AthleteNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})

    @app.exception_handler(TestNotFoundError)
    async def test_not_found_handler(request: Request, exc: TestNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})

    @app.exception_handler(VideoNotFoundError)
    async def video_not_found_handler(request: Request, exc: VideoNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})

    @app.exception_handler(MetricsNotFoundError)
    async def metrics_not_found_handler(request: Request, exc: MetricsNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})

    @app.exception_handler(InvalidCredentialsError)
    async def invalid_credentials_handler(request: Request, exc: InvalidCredentialsError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": str(exc)})
