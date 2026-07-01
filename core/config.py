from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = ""

    SECRET_KEY: str = ""
    ALGORITHM: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30 

    NOMBA_CLIENT_ID: str = ""
    NOMBA_CLIENT_SECRET: str = ""
    NOMBA_ACCOUNT_ID: str = ""
    NOMBA_BASE_URL: str = ""
    NOMBA_WEBHOOK_SECRET: str = ""

    TERMII_API_KEY: str = ""

    class Config:
        env_file = ".env"


settings = Settings()