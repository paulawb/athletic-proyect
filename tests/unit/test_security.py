from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_hash_and_verify_password_roundtrip() -> None:
    hashed = hash_password("Sprint#2026")

    assert hashed != "Sprint#2026"
    assert verify_password("Sprint#2026", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_create_and_decode_access_token_roundtrip() -> None:
    token = create_access_token(subject="coach@institucion.edu")

    subject = decode_access_token(token)

    assert subject == "coach@institucion.edu"


def test_decode_invalid_token_raises_invalid_credentials() -> None:
    import pytest

    from app.core.exceptions import InvalidCredentialsError

    with pytest.raises(InvalidCredentialsError):
        decode_access_token("token-que-no-existe")
