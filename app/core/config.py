"""
Centralised application settings.

All configuration is sourced from environment variables (see `.env.example`).
Never hardcode secrets — this module only defines shape + defaults for local dev.
"""

from functools import lru_cache
from urllib.parse import quote

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────
    APP_NAME: str = "Mendyr"
    ENVIRONMENT: str = "local"  # local | dev | staging | production
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    SECRET_KEY: str
    ALLOWED_HOSTS: list[str] = ["*"]
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # ── Database ─────────────────────────────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "mendyr"
    POSTGRES_PASSWORD: str = "mendyr"
    POSTGRES_DB: str = "mendyr"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False
    # Hosted Postgres (Supabase, RDS, etc.) requires TLS on the wire.
    POSTGRES_SSL_REQUIRED: bool = False
    # Supabase's "Transaction" pooler (PgBouncer, port 6543) doesn't support asyncpg's
    # prepared-statement cache — every reused statement name collides across pooled
    # connections. Set this when POSTGRES_PORT points at that pooler; leave off for a direct
    # connection or the "Session" pooler (port 5432), both of which support prepared statements.
    DB_DISABLE_PREPARED_STATEMENT_CACHE: bool = False

    @computed_field  # type: ignore[misc]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        # URL-encode user/password — a raw password containing '@', ':', '/', etc. (common in
        # generated DB passwords, e.g. Supabase's) would otherwise be misparsed as part of the
        # host, silently connecting to the wrong hostname or failing DNS resolution entirely.
        user = quote(self.POSTGRES_USER, safe="")
        password = quote(self.POSTGRES_PASSWORD, safe="")
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field  # type: ignore[misc]
    @property
    def SQLALCHEMY_SYNC_DATABASE_URI(self) -> str:
        """Sync driver URL — used by Alembic migrations."""
        user = quote(self.POSTGRES_USER, safe="")
        password = quote(self.POSTGRES_PASSWORD, safe="")
        base = (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
        return f"{base}?sslmode=require" if self.POSTGRES_SSL_REQUIRED else base

    # ── Redis / Celery ───────────────────────────────────────────────────
    # Set false to run without a Redis instance at all: rate limiting falls back to an
    # in-process (single-worker-process-only) store. Fine for early local/dev use;
    # Celery worker/beat still need real Redis to run
    # (background jobs just won't be sent anywhere if you're not running those processes).
    REDIS_ENABLED: bool = True
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ── Auth ─────────────────────────────────────────────────────────────
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 60

    # Also set the refresh token as an httponly cookie (in addition to the response body),
    # so browser clients can rely on it without storing the token in JS-accessible storage.
    REFRESH_TOKEN_COOKIE_ENABLED: bool = True
    REFRESH_TOKEN_COOKIE_NAME: str = "refresh_token"

    # ── Marketplace rules ────────────────────────────────────────────────
    PLATFORM_COMMISSION_PCT: float = 20
    GST_PCT: float = 18
    DEFAULT_SEARCH_RADIUS_KM: float = 12
    MAX_SEARCH_RADIUS_KM: float = 30
    BOOKING_OFFER_TTL_SECONDS: int = 60
    BOOKING_MAX_OFFER_ROUNDS: int = 4
    FREE_CANCELLATION_WINDOW_MINUTES: int = 60
    CANCELLATION_FEE_PCT: float = 25
    VISIT_CHECKIN_GEOFENCE_METERS: int = 300

    # ── Payments ─────────────────────────────────────────────────────────
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # ── SMS ──────────────────────────────────────────────────────────────
    SMS_PROVIDER: str = "console"  # console | msg91 | twilio
    MSG91_AUTH_KEY: str = ""
    MSG91_SENDER_ID: str = "MENDYR"
    MSG91_OTP_TEMPLATE_ID: str = ""

    # ── Push ─────────────────────────────────────────────────────────────
    FCM_PROJECT_ID: str = ""
    FCM_CREDENTIALS_JSON: str = ""

    # ── Storage ──────────────────────────────────────────────────────────
    S3_BUCKET: str = "mendyr-dev"
    S3_REGION: str = "ap-south-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    S3_ENDPOINT_URL: str | None = None
    PRESIGNED_URL_TTL_SECONDS: int = 900

    # ── Maps ─────────────────────────────────────────────────────────────
    GOOGLE_MAPS_API_KEY: str = ""

    # ── Observability ────────────────────────────────────────────────────
    SENTRY_DSN: str = ""
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False

    @computed_field  # type: ignore[misc]
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    """Settings are cached — env is read once per process."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
