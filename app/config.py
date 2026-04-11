import os

from dotenv import load_dotenv
from pydantic import BaseModel


# Load values from the .env file into environment variables.
load_dotenv()


class Settings(BaseModel):
    """Simple app settings loaded from environment variables."""

    # This is the MySQL connection string used by database.py.
    database_url: str = os.getenv(
        "DATABASE_URL",
        "mysql+mysqlconnector://root:password@localhost:3306/assistant_db",
    )
    # JWT uses this secret key to sign and verify tokens.
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "change-me")
    jwt_algorithm: str = "HS256"
    # Google AI Studio is used for chat, summaries, routing fallback, and images.
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    # OpenWeatherMap is used for simple weather tool responses.
    openweather_api_key: str = os.getenv("OPENWEATHER_API_KEY", "")
    # Smaller text model for normal chat and summaries.
    text_model: str = os.getenv("TEXT_MODEL", "gemini-2.5-flash-lite")
    # Stronger Gemini model for image analysis and other heavier tasks.
    vision_model: str = os.getenv("VISION_MODEL", "gemini-2.5-flash")


# Create one settings object that other files can import.
settings = Settings()
