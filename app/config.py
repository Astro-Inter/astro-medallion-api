from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    api_token: SecretStr = Field(default=SecretStr(""))
    database_url: SecretStr = Field(default=SecretStr(""))
    database_ssl_ca: SecretStr = Field(default=SecretStr(""))
    database_ssl_ca_file: Path | None = None
