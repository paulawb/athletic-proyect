from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

# Connection pool: tamaños y timeouts sintonizados para un backend de analysis
# (pocas conexiones concurrentes, pero videos largos = sesiones largas).
engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_pre_ping=True,
    pool_recycle=3600,
)

AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


class Base(DeclarativeBase):
    """Clase base declarativa para todos los modelos SQLAlchemy de infraestructura."""


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependencia de FastAPI que entrega una sesion de base de datos por request."""
    async with AsyncSessionLocal() as session:
        yield session
