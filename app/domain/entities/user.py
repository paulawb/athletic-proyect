from dataclasses import dataclass
from datetime import datetime


@dataclass
class User:
    """Entidad mínima de cuenta para autenticación y propiedad de datos."""

    email: str
    hashed_password: str
    full_name: str
    id: int | None = None
    phone: str | None = None
    role: str = "docente"
    is_active: bool = True
    created_at: datetime | None = None
