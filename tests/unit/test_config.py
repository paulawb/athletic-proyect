from app.core.config import Settings


def test_settings_converts_render_postgres_url_to_asyncpg_driver() -> None:
    settings = Settings(
        database_url="postgresql://athlete:password@db.example/athletic",
        jwt_secret_key="test-secret",
    )

    assert settings.database_url == "postgresql+asyncpg://athlete:password@db.example/athletic"


def test_settings_preserves_existing_asyncpg_driver() -> None:
    database_url = "postgresql+asyncpg://athlete:password@db.example/athletic"
    settings = Settings(database_url=database_url, jwt_secret_key="test-secret")

    assert settings.database_url == database_url
