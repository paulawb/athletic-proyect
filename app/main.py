from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.presentation.api.v1.routes import analisis, atletas, auth, health, pruebas, videos, workspace

settings = get_settings()

configure_logging()

app = FastAPI(
    title="Athletic Analysis API",
    description=(
        "Sistema de analisis de video basado en drones autonomos para la "
        "evaluacion de variables de desempeno en carreras de velocidad."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "Content-Disposition"],
)

register_exception_handlers(app)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(atletas.router)
app.include_router(pruebas.router)
app.include_router(videos.router)
app.include_router(analisis.router)
app.include_router(workspace.router)

_STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"
if (_STATIC_ROOT / "index.html").is_file():
    _STATIC_ROOT = _STATIC_ROOT.resolve()
    app.mount("/assets", StaticFiles(directory=_STATIC_ROOT / "assets"), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    async def frontend_index() -> FileResponse:
        return FileResponse(_STATIC_ROOT / "index.html")

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend_route(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Recurso no encontrado")
        requested_path = (_STATIC_ROOT / path).resolve()
        if not requested_path.is_relative_to(_STATIC_ROOT):
            raise HTTPException(status_code=404, detail="Recurso no encontrado")
        if requested_path.is_file():
            return FileResponse(requested_path)
        if Path(path).suffix:
            raise HTTPException(status_code=404, detail="Recurso no encontrado")
        return FileResponse(_STATIC_ROOT / "index.html")
