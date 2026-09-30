"""
Configuración central de TriageAI Backend.
Todos los valores se pueden sobreescribir con variables de entorno o un archivo .env,
pero nunca dependen de servicios externos: todo corre on-premise.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # -- Base de datos --
    # SQLite alcanza para un solo puesto de triaje. Para varios puestos concurrentes,
    # cambiar a algo como: "postgresql://usuario:pass@localhost/triageai"

    catboost_model_path: str = "app/ml/artifacts/triage_catboost_model.joblib"
    site_id: str = "SITE-HEL-01"   

    database_url: str = "sqlite:///./triageai.db"

    # -- Ollama --
    ollama_url: str = "http://localhost:11434"
    ollama_timeout_seconds: int = 60

    # -- Seguridad / JWT --
    # ⚠️ CAMBIAR en producción. Generar con: python -c "import secrets; print(secrets.token_hex(32))"
    secret_key: str = "CAMBIAR-ESTA-CLAVE-EN-PRODUCCION-1707"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 horas, dura un turno de guardia

    # -- CORS --
    # Orígenes permitidos para que el frontend (HTML servido en :8080) pueda llamar a la API (:8000)
    allowed_origins: list[str] = [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]

    # -- Usuario admin inicial (se crea solo si la tabla de usuarios está vacía) --
    seed_admin_username: str = "admin"
    seed_admin_password: str = "cambiar123"  # ⚠️ cambiar tras el primer login

    class Config:
        env_file = ".env"


settings = Settings()
