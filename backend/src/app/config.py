"""Cấu hình ứng dụng qua biến môi trường (xem .env.example ở thư mục gốc)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "local"
    database_url: str = "postgresql+asyncpg://tlmn:tlmn@localhost:5432/tlmn"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    allowed_origins: list[str] = ["http://localhost:5173"]

    # Admin session (ADR-012)
    cookie_secure: bool = False  # bật True ở môi trường có HTTPS
    admin_session_hours: int = 12
    admin_max_failed_logins: int = 10
    admin_lock_minutes: int = 15
    login_rate_limit_per_minute: int = 5

    # Guest + phòng (slice S2)
    guest_token_days: int = 30
    room_create_per_hour: int = 10
    room_lookup_per_minute: int = 30  # chống dò mã phòng
    ws_auth_timeout_seconds: float = 5.0
    ws_max_messages_per_second: int = 10
    ws_max_frame_bytes: int = 4096
    seat_sweep_interval_seconds: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
