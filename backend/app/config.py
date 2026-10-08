from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GROQ_API_KEY: str = ""
    JWT_SECRET: str = "placeiq-super-secret-key-2026"
    DATABASE_URL: str = "sqlite:///./placeiq.db"
    FRONTEND_URL: str = "http://localhost:5173"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()