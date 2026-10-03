from typing import Awaitable, Callable

from fastapi import BackgroundTasks

from app.application.ports.task_runner import TaskRunner


class BackgroundTasksRunner(TaskRunner):
    """Implementacion inicial (academica) usando fastapi.BackgroundTasks.

    Limitaciones conocidas, documentadas para la migracion futura a
    Celery + Redis (seccion 12):
    - Corre en el mismo proceso y event loop que la API: una tarea CPU-bound
      larga (OpenCV cuadro por cuadro) puede degradar la capacidad de
      respuesta de otras peticiones si no se delega a un threadpool.
    - No sobrevive un reinicio o caida del servidor: una tarea en curso se
      pierde por completo.
    - No escala horizontalmente entre multiples workers/instancias.
    - No tiene reintentos, colas con prioridad, ni visibilidad de estado
      fuera del propio proceso.
    """

    def __init__(self, background_tasks: BackgroundTasks) -> None:
        self._background_tasks = background_tasks

    def enqueue(self, job: Callable[[], Awaitable[None]]) -> None:
        self._background_tasks.add_task(job)
