import os

# Variables minimas requeridas por Settings para que la app se pueda
# importar en pruebas sin depender de un .env real ni de Postgres vivo.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/athletic_analysis_test",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("ENVIRONMENT", "test")
