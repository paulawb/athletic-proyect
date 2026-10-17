from app.core.config import Settings


def test_settings_converts_neon_ssl_query_for_asyncpg() -> None:
    settings = Settings(
        database_url=(
            "postgresql://user:password@ep.example/athletic"
            "?sslmode=require&channel_binding=require"
        ),
        jwt_secret_key="test-secret",
    )

    assert settings.database_url == (
        "postgresql+asyncpg://user:password@ep.example/athletic?ssl=require"
    )
