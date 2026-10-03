from uuid import uuid4

from app.core.exceptions import (
    InvalidVideoFormatError,
    TestNotFoundError,
    VideoProcessingError,
)
from app.domain.entities.video import Video, VideoStatus
from app.domain.repositories.test_repository import TestRepository
from app.domain.repositories.video_repository import VideoRepository
from app.domain.services.frame_processor import FrameProcessor
from app.domain.services.video_storage import UploadedFileLike, VideoStorage

ALLOWED_EXTENSIONS = {".mp4", ".mov"}
ALLOWED_CONTENT_TYPES = {"video/mp4", "video/quicktime"}


class UploadVideo:
    """Caso de uso de la Fase 3: valida, guarda y registra el video de una
    prueba (seccion 7). No procesa cuadros ni crea un Analysis todavia
    -eso llega con las Fases 4 y 8-, pero sí obtiene los metadatos basicos
    del video (fps, duracion, resolucion, total de cuadros) para dejarlos
    persistidos desde ya."""

    def __init__(
        self,
        test_repository: TestRepository,
        video_repository: VideoRepository,
        video_storage: VideoStorage,
        frame_processor: FrameProcessor,
        max_size_bytes: int,
    ) -> None:
        self._test_repository = test_repository
        self._video_repository = video_repository
        self._video_storage = video_storage
        self._frame_processor = frame_processor
        self._max_size_bytes = max_size_bytes

    async def execute(self, test_id: int, file: UploadedFileLike) -> Video:
        test = await self._test_repository.get_by_id(test_id)
        if test is None:
            raise TestNotFoundError(f"No existe una prueba con id={test_id}")

        self._validate_extension_and_type(file)

        destination_id = f"test-{test_id}-{uuid4().hex}"
        stored = await self._video_storage.save(file, destination_id, max_size_bytes=self._max_size_bytes)

        if stored.file_size == 0:
            await self._video_storage.delete(stored.storage_path)
            raise InvalidVideoFormatError("El archivo de video esta vacio")

        try:
            metadata = self._frame_processor.get_video_metadata(
                self._video_storage.get_absolute_path(stored.storage_path)
            )
        except Exception as exc:
            await self._video_storage.delete(stored.storage_path)
            raise VideoProcessingError("El video no se pudo leer; puede estar corrupto") from exc

        if metadata.total_frames <= 0:
            await self._video_storage.delete(stored.storage_path)
            raise VideoProcessingError("El video no contiene fotogramas legibles")

        video = Video(
            test_id=test_id,
            original_filename=file.filename or "video.mp4",
            storage_path=stored.storage_path,
            file_size=stored.file_size,
            duration=metadata.duration,
            fps=metadata.fps,
            width=metadata.width,
            height=metadata.height,
            total_frames=metadata.total_frames,
            status=VideoStatus.VALIDATED,
        )
        return await self._video_repository.create(video)

    @staticmethod
    def _validate_extension_and_type(file: UploadedFileLike) -> None:
        filename = file.filename or ""
        extension = f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else ""
        if extension not in ALLOWED_EXTENSIONS:
            raise InvalidVideoFormatError(
                f"Extension de video no permitida: '{extension or 'desconocida'}'. "
                f"Formatos permitidos: MP4, MOV"
            )

        content_type = file.content_type
        if content_type is not None and content_type not in ALLOWED_CONTENT_TYPES:
            raise InvalidVideoFormatError(f"Tipo de contenido no permitido: '{content_type}'")
