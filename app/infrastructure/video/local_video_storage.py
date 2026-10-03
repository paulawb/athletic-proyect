from pathlib import Path

from app.core.exceptions import VideoTooLargeError
from app.domain.services.video_storage import StoredVideo, UploadedFileLike, VideoStorage

_CHUNK_SIZE = 1024 * 1024  # 1 MB por lectura: nunca se carga el video completo en memoria.


class LocalVideoStorage(VideoStorage):
    """Almacena videos en disco local, dentro de <base_path>/videos/.
    Implementacion de la Fase 3. S3VideoStorage podra reemplazarla despues
    sin que ningun caso de uso cambie, porque ambas implementan VideoStorage."""

    def __init__(self, base_path: str) -> None:
        self._base_path = Path(base_path)
        self._videos_dir = self._base_path / "videos"
        self._videos_dir.mkdir(parents=True, exist_ok=True)

    async def save(
        self, file: UploadedFileLike, destination_id: str, max_size_bytes: int | None = None
    ) -> StoredVideo:
        extension = Path(file.filename or "").suffix.lower() or ".mp4"
        relative_path = f"videos/{destination_id}{extension}"
        absolute_path = self._base_path / relative_path

        bytes_written = 0
        try:
            with open(absolute_path, "wb") as destination:
                while chunk := await file.read(_CHUNK_SIZE):
                    bytes_written += len(chunk)
                    if max_size_bytes is not None and bytes_written > max_size_bytes:
                        raise VideoTooLargeError(
                            f"El video supera el tamano maximo permitido "
                            f"({max_size_bytes // (1024 * 1024)} MB)"
                        )
                    destination.write(chunk)
        except Exception:
            absolute_path.unlink(missing_ok=True)
            raise

        return StoredVideo(storage_path=relative_path, file_size=bytes_written)

    def get_absolute_path(self, storage_path: str) -> str:
        return str((self._base_path / storage_path).resolve())

    async def delete(self, storage_path: str) -> None:
        Path(self.get_absolute_path(storage_path)).unlink(missing_ok=True)
