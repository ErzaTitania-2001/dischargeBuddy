import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Settings:
    PROJECT_NAME: str = "DischargeBuddy"
    VERSION: str = "1.0.0"
    MODEL_API_KEY: str = os.getenv("MODEL_API_KEY", "")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "muse-spark-1.3")
    MODEL_API_BASE_URL: str = os.getenv("MODEL_API_BASE_URL", "https://api.meta.ai/v1")
    EMERGENCY_NUMBER: str = os.getenv("EMERGENCY_NUMBER", "911")
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
    DATABASE_PATH: Path = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "dischargebuddy.sqlite3"))).resolve()
    DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()
    UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", str(DATA_DIR / "uploads"))).resolve()
    STORAGE_BUCKET: str = os.getenv("STORAGE_BUCKET", "").strip()
    BREVO_API_KEY: str = os.getenv("BREVO_API_KEY", "").strip()
    BREVO_SENDER_EMAIL: str = os.getenv("BREVO_SENDER_EMAIL", "").strip()
    BREVO_SENDER_NAME: str = os.getenv("BREVO_SENDER_NAME", "DischargeBuddy").strip()
    EMAIL_NOTIFICATIONS_ENABLED: bool = os.getenv("EMAIL_NOTIFICATIONS_ENABLED", "false").lower() in ("1", "true", "yes")
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:8080").rstrip("/")
    SCHEDULER_SERVICE_ACCOUNT_EMAIL: str = os.getenv("SCHEDULER_SERVICE_ACCOUNT_EMAIL", "").strip()
    MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
    SESSION_TTL_DAYS: int = int(os.getenv("SESSION_TTL_DAYS", "30"))
    CORS_ORIGINS: list[str] = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080").split(",") if origin.strip()]
    COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "false").lower() in ("1", "true", "yes")
    PORT: int = int(os.getenv("PORT", "8080"))
    HOST: str = os.getenv("HOST", "0.0.0.0")

settings = Settings()
if os.getenv("K_SERVICE") and (not settings.DATABASE_URL or not settings.STORAGE_BUCKET):
    raise RuntimeError("Cloud Run requires DATABASE_URL and STORAGE_BUCKET for durable patient data.")
