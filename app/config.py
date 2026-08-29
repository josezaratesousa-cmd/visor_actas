"""Runtime settings.

Everything configurable is read from a .env file that lives OUTSIDE the
repository. There is no default copy inside the project tree, so a
misconfigured deployment fails loudly instead of silently running with
placeholder credentials.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Where the .env lives is a deployment decision, not a property of the code.
# APP_ENV_FILE names it; the fallback is a conventional system path. Nothing
# here points at a particular host or account.
DEFAULT_ENV_FILE = os.getenv("APP_ENV_FILE", "/etc/visor-actas/.env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "staging", "production"] = "development"
    app_base_url: str = "http://localhost:8081"
    app_root_path: str = ""
    app_default_locale: Literal["es", "en"] = "es"
    app_default_theme: Literal["light", "dark"] = "light"

    stamping_base_url: str = "https://api.stamping.io"
    stamping_token: str = Field(default="", repr=False)
    stamping_timeout: int = 30

    custody_driver: Literal["local", "s3"] = "local"
    custody_path: Path = Path("/tmp/custody")
    custody_bucket: str = ""
    custody_region: str = ""
    custody_endpoint: str = ""
    custody_access_key: str = Field(default="", repr=False)
    custody_secret_key: str = Field(default="", repr=False)

    code_cipher_key: str = Field(default="", repr=False)
    cache_path: Path = Path("/tmp/custody/cache")

    # ── Anchors ──────────────────────────────────────────────────────
    # Networks the platform writes to, and where to send a citizen who
    # wants to see the record for themselves. Defaults match the current
    # deployment; an explorer that moves, or a chain id that changes, is
    # a line in the .env rather than a release.
    ipfs_gateway: str = "https://ipfs.stamping.io/{value}"
    lacchain_chain_id: str = "648541"
    lacchain_explorer: str = "https://explorer.lacnet.com/tx/{value}"
    rollux_chain_id: str = "570"
    rollux_explorer: str = "https://explorer.rollux.com/tx/{value}"
    merkle_viewer: str = "https://stamping.io/es/view/?{trxid}"

    # ── Throttling ───────────────────────────────────────────────────
    # Generous on purpose. Mobile carriers put tens of thousands of
    # subscribers behind one address, so a tight limit locks out a city
    # rather than an abuser. See app/services/ratelimit.py.
    rate_limit_per_second: float = 4.0
    rate_limit_burst: int = 60
    rate_limit_enabled: bool = True

    # How long an attested record may be served from memory. The record
    # itself does not change, so this only delays noticing a new
    # attestation for a sheet that was pending.
    record_cache_seconds: int = 60

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
