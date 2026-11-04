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
    PORT: int = int(os.getenv("PORT", "8080"))
    HOST: str = os.getenv("HOST", "0.0.0.0")

settings = Settings()
