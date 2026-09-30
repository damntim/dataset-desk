from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings. Each field can be overridden by an environment variable
    with the same name in capitals (e.g. DATABASE_URL) or by a .env file."""

    database_url: str = "postgresql+psycopg://desk:desk@localhost:5432/desk"
    jwt_secret: str = "dev-only-change-me"
    jwt_expire_minutes: int = 60
    seed_dir: str = "../seed"  # folder holding users.json and episodes.csv

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
