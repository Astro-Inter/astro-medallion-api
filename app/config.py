from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    api_token: SecretStr = Field(default=SecretStr(""))
    database_url: SecretStr = Field(default=SecretStr(""))
    database_ssl_ca: SecretStr = Field(default=SecretStr(""))
    database_ssl_ca_file: Path | None = None
    snapshot_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    max_snapshot_rows: int = Field(default=100000, ge=1000, le=1000000)
    rate_limit_per_minute: int = Field(default=120, ge=1, le=10000)
    retry_after_seconds: int = Field(default=5, ge=1, le=300)
