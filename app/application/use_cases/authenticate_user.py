from app.core.exceptions import InvalidCredentialsError
from app.core.security import create_access_token, verify_password
from app.domain.entities.user import User
from app.domain.repositories.user_repository import UserRepository


class AuthenticateUser:
    """Caso de uso: valida credenciales y emite un token de acceso.

    No conoce FastAPI ni SQLAlchemy directamente: solo depende de la
    interfaz UserRepository (inyectada) y de utilidades de seguridad sin
    acoplamiento a infraestructura. La verificación de contraseña y la
    emisión del token -reglas de negocio- viven aquí, no en el router.
    """

    def __init__(self, user_repository: UserRepository) -> None:
        self._user_repository = user_repository

    async def execute(self, email: str, password: str) -> str:
        user: User | None = await self._user_repository.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError("Correo o contraseña incorrectos")
        if not user.is_active:
            raise InvalidCredentialsError("El usuario está inactivo")
        return create_access_token(subject=user.email)
