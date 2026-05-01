from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Incident Management System"
    mongo_url: str = "mongodb://mongo:27017"
    mongo_db: str = "ims"
    postgres_url: str = "postgresql+psycopg://ims:ims@postgres:5432/ims"
    redis_url: str = "redis://redis:6379/0"

    queue_max_size: int = 50000
    debounce_window_seconds: int = 10
    rate_limit_per_second: int = 10000
    throughput_log_interval_seconds: int = 5
    worker_count: int = 2


settings = Settings()
