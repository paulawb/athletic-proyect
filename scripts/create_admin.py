"""Crea el primer usuario (entrenador/administrador) del sistema.

No hay endpoint de registro publico -por diseno, es una app institucional
administrada- asi que el primer acceso se crea con este script.

Uso:
    python -m scripts.create_admin correo@institucion.edu "Contrasena123" "Nombre Apellido"
"""
import asyncio
import sys

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.domain.entities.user import User
from app.infrastructure.database.repositories.user_repository_impl import SqlAlchemyUserRepository


async def main(email: str, password: str, full_name: str) -> None:
    async with AsyncSessionLocal() as session:
        repository = SqlAlchemyUserRepository(session)
        existing = await repository.get_by_email(email)
        if existing is not None:
            print(f"Ya existe un usuario con el correo {email}")
            return

        user = User(email=email, hashed_password=hash_password(password), full_name=full_name)
        created = await repository.create(user)
        print(f"Usuario creado con id={created.id} ({created.email})")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print('Uso: python -m scripts.create_admin <email> <password> "<nombre completo>"')
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3]))
