from abc import ABC, abstractmethod
from typing import Awaitable, Callable


class TaskRunner(ABC):
    """Abstrae el mecanismo de ejecucion de trabajos en segundo plano
    (seccion 12). BackgroundTasksRunner es la implementacion de Fase 8;
    CeleryTaskRunner / RQTaskRunner llegaran despues sin cambiar los casos
    de uso que dependen de esta interfaz."""

    @abstractmethod
    def enqueue(self, job: Callable[[], Awaitable[None]]) -> None: ...
