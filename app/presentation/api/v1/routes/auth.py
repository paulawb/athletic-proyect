from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.authenticate_user import AuthenticateUser
from app.core.database import get_db_session
from app.core.phone import normalize_phone
from app.core.security import create_access_token, hash_password
from app.domain.entities.user import User
from app.infrastructure.database.models.user_model import UserModel
from app.infrastructure.database.repositories.user_repository_impl import SqlAlchemyUserRepository
from app.presentation.api.v1.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class UserRegistrationDTO(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=20)
    password: str = Field(min_length=10, max_length=72)
    role: Literal["docente", "estudiante"]

    @field_validator("full_name")
    @classmethod
    def trim_full_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("El nombre debe tener al menos 2 caracteres")
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        try:
            return normalize_phone(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("La contraseña no puede superar 72 bytes")
        return value


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegistrationDTO,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    email = str(data.email).lower()
    existing_user = await session.scalar(
        select(UserModel.id).where(func.lower(UserModel.email) == email)
    )
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese correo electrónico")

    user = UserModel(
        email=email,
        full_name=data.full_name,
        phone=data.phone,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Ya existe una cuenta con ese correo electrónico",
        ) from exc

    return {
        "access_token": create_access_token(email),
        "token_type": "bearer",
        "email": email,
        "full_name": user.full_name,
        "role": user.role,
    }


@router.post("/token")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    repository = SqlAlchemyUserRepository(session)
    token = await AuthenticateUser(repository).execute(
        email=form_data.username,
        password=form_data.password,
    )
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
async def read_current_user(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "email": current_user.email,
        "full_name": current_user.full_name,
        "phone": current_user.phone,
        "role": current_user.role,
    }
