import pytest

from app.application.use_cases.authenticate_user import AuthenticateUser
from app.core.exceptions import InvalidCredentialsError
from app.core.security import hash_password
from app.domain.entities.user import User
from app.domain.repositories.user_repository import UserRepository


class FakeUserRepository(UserRepository):
    """Repositorio en memoria: prueba el caso de uso sin tocar Postgres."""

    def __init__(self, users: list[User]) -> None:
        self._users = {user.email: user for user in users}

    async def get_by_email(self, email: str) -> User | None:
        return self._users.get(email)

    async def create(self, user: User) -> User:
        self._users[user.email] = user
        return user


def _build_user(email: str, password: str, is_active: bool = True) -> User:
    return User(
        email=email,
        hashed_password=hash_password(password),
        full_name="Entrenador de prueba",
        is_active=is_active,
    )


async def test_authenticate_user_returns_token_with_valid_credentials() -> None:
    repository = FakeUserRepository([_build_user("coach@institucion.edu", "Sprint#2026")])
    use_case = AuthenticateUser(repository)

    token = await use_case.execute("coach@institucion.edu", "Sprint#2026")

    assert isinstance(token, str) and len(token) > 0


async def test_authenticate_user_rejects_wrong_password() -> None:
    repository = FakeUserRepository([_build_user("coach@institucion.edu", "Sprint#2026")])
    use_case = AuthenticateUser(repository)

    with pytest.raises(InvalidCredentialsError):
        await use_case.execute("coach@institucion.edu", "contraseña-incorrecta")


async def test_authenticate_user_rejects_unknown_email() -> None:
    repository = FakeUserRepository([])
    use_case = AuthenticateUser(repository)

    with pytest.raises(InvalidCredentialsError):
        await use_case.execute("nadie@institucion.edu", "cualquier-cosa")


async def test_authenticate_user_rejects_inactive_user() -> None:
    repository = FakeUserRepository(
        [_build_user("coach@institucion.edu", "Sprint#2026", is_active=False)]
    )
    use_case = AuthenticateUser(repository)

    with pytest.raises(InvalidCredentialsError):
        await use_case.execute("coach@institucion.edu", "Sprint#2026")
