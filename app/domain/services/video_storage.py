from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol


class UploadedFileLike(Protocol):
    """Abstraccion minima de un archivo subido. Evita que el dominio dependa
    directamente de fastapi.UploadFile (regla de la seccion 4: la logica de
    negocio no depende de FastAPI)."""

    filename: str | None
    content_type: str | None

    async def read(self, size: int = -1) -> bytes: ...


@dataclass(frozen=True)
class StoredVideo:
    storage_path: str
    file_size: int


class VideoStorage(ABC):
    @abstractmethod
    async def save(
        self, file: UploadedFileLike, destination_id: str, max_size_bytes: int | None = None
    ) -> StoredVideo:
        """Escribe el archivo progresivamente (streaming); nunca lo carga
        completo en memoria. Si max_size_bytes se supera durante la
        escritura, aborta y elimina el archivo parcial: no tiene sentido
        terminar de escribir a disco un archivo que ya sabemos que se va a
        rechazar. LocalVideoStorage es la implementacion de Fase 3;
        S3VideoStorage se agregara despues sin cambiar esta interfaz."""
        ...

    @abstractmethod
    def get_absolute_path(self, storage_path: str) -> str: ...

    @abstractmethod
    async def delete(self, storage_path: str) -> None: ...
