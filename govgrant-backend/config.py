from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = "dev_secret_change_in_production"
    DATABASE_URL: str = "sqlite:///./govgrant.db"
    GOOGLE_API_KEY: str = ""
    SENDGRID_API_KEY: str = ""
    FRONTEND_URL: str = "http://localhost:3000"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7
    CHROMA_DB_PATH: str = "./data/chroma_db"
    GEMINI_MODEL: str = "gemini-2.0-flash"
    SQLITE_URL: str = "sqlite:///./data/govgrant.db"

    model_config = {
        "env_file": ".env",
        "extra": "ignore"
    }


settings = Settings()
