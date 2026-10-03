from dataclasses import dataclass
from datetime import datetime


@dataclass
class User:
    """Entidad minima para autenticacion (Fase 1). El perfil completo del
    entrenador/institucion (mostrado en las maquetas de Configuracion) se
    disenara cuando se aborde esa pantalla en una fase posterior."""

    email: str
    hashed_password: str
    full_name: str
    id: int | None = None
    phone: str | None = None
    role: str = "docente"
    is_active: bool = True
    created_at: datetime | None = None
