from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.exceptions import InvalidCredentialsError

settings = get_settings()


def hash_password(plain_password: str) -> str:
    """Hashea una contrase\u00f1a con bcrypt. Las contrase\u00f1as longer than 72
    bytes are truncated automatically by bcrypt (per the bcrypt spec)."""
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contrase\u00f1a plana contra su hash bcrypt."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        # Hash mal formado (no es un bcrypt v\u00e1lido): no coincide.
        return False


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise InvalidCredentialsError("Token invalido o expirado") from exc
    subject = payload.get("sub")
    if subject is None:
        raise InvalidCredentialsError("Token invalido: no contiene subject")
    return subject