import re

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    GROQ_API_KEY: str = ""
    JWT_SECRET: str = "placeiq-super-secret-key-2026"
    DATABASE_URL: str = "sqlite:///./placeiq.db"
    FRONTEND_URL: str = "http://localhost:5173"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080
    PREMIUM_PRICE_DISPLAY: str = "Pricing not configured"
    PREMIUM_BILLING_PERIOD_DISPLAY: str = ""
    PREMIUM_AMOUNT_MINOR: int | None = Field(default=None, gt=0)
    PREMIUM_CURRENCY: str = "INR"
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    @field_validator("PREMIUM_CURRENCY")
    @classmethod
    def validate_premium_currency(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise ValueError("PREMIUM_CURRENCY must be a three-letter uppercase code")
        return value

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()