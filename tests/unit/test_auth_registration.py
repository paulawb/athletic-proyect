import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.security import decode_access_token, verify_password
from app.infrastructure.database.models.user_model import UserModel
from app.presentation.api.v1.routes import auth


class FakeSession:
    def __init__(self, scalar_values: list[object | None]) -> None:
        self.scalar_values = scalar_values
        self.user: UserModel | None = None
        self.commits = 0
        self.rollbacks = 0

    async def scalar(self, _query):
        if self.scalar_values:
            return self.scalar_values.pop(0)
        return self.user

    def add(self, user: UserModel) -> None:
        self.user = user

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


async def test_register_creates_account_and_returns_login_token() -> None:
    session = FakeSession([None])
    data = auth.UserRegistrationDTO(
        full_name="  Ana Entrenadora  ",
        email="ANA@ejemplo.com",
        phone="+57 (300) 123-4567",
        password="UnaClaveSegura2026",
        role="estudiante",
    )

    response = await auth.register(data, session)

    assert response["email"] == "ana@ejemplo.com"
    assert response["role"] == "estudiante"
    assert session.user is not None
    assert session.user.full_name == "Ana Entrenadora"
    assert session.user.phone == "+573001234567"
    assert session.user.role == "estudiante"
    assert verify_password("UnaClaveSegura2026", session.user.hashed_password)
    assert decode_access_token(response["access_token"]) == "ana@ejemplo.com"
    assert session.commits == 1


async def test_register_rejects_duplicate_email() -> None:
    session = FakeSession([1])
    data = auth.UserRegistrationDTO(
        full_name="Ana Entrenadora",
        email="ana@ejemplo.com",
        phone="3001234567",
        password="UnaClaveSegura2026",
        role="docente",
    )
    with pytest.raises(HTTPException) as error:
        await auth.register(data, session)
    assert error.value.status_code == 409
    assert session.commits == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"full_name": "A", "email": "ana@ejemplo.com", "phone": "3001234567", "password": "UnaClaveSegura2026", "role": "docente"},
        {"full_name": "Ana", "email": "no-es-correo", "phone": "3001234567", "password": "UnaClaveSegura2026", "role": "docente"},
        {"full_name": "Ana", "email": "ana@ejemplo.com", "phone": "12", "password": "UnaClaveSegura2026", "role": "docente"},
        {"full_name": "Ana", "email": "ana@ejemplo.com", "phone": "ABC1234567", "password": "UnaClaveSegura2026", "role": "docente"},
        {"full_name": "Ana", "email": "ana@ejemplo.com", "phone": "3001234567", "password": "corta", "role": "docente"},
        {"full_name": "Ana", "email": "ana@ejemplo.com", "phone": "3001234567", "password": "á" * 37, "role": "docente"},
        {"full_name": "Ana", "email": "ana@ejemplo.com", "phone": "3001234567", "password": "UnaClaveSegura2026", "role": "administrador"},
    ],
)
def test_registration_validates_every_account_field(payload: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        auth.UserRegistrationDTO(**payload)
