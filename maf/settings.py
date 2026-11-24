"""Configuration, read once from the environment at startup.

Every secret and path is an environment variable (see docs in NOTES.md). Nothing
here writes anything to disk.
"""

import importlib.util
import os
from dataclasses import dataclass, field
from pathlib import Path

PRODUCTION = "production"
# "minerv" as alphabet positions (m13 i9 n14 e5 r18 v22), cut to six digits. Local development only.
DEV_LOGIN_CODE = "139145"
EMAIL_BACKENDS = {"ses", "azure", "console"}


# The name filter's spaCy model; it must match the model pyproject.toml installs.
DEFAULT_SPACY_MODEL = "en_core_web_md"


class ConfigError(Exception):
    """The environment is not usable; the app must refuse to start."""


@dataclass(frozen=True)
class Settings:
    env: str = "development"
    database_path: Path = Path("maf.db")
    label_secret: bytes = b""
    signing_key_path: Path | None = None
    session_secret: bytes = b""
    maintainer_email: str = ""
    email_backend: str = "ses"
    email_from: str = ""
    aws_region: str = "us-east-1"
    azure_email_connection: str = ""
    name_filter_threshold: float = 0.85
    name_filter_enabled: bool = True
    spacy_model: str = DEFAULT_SPACY_MODEL
    base_url: str = "http://localhost:8000"
    static_dir: Path = field(default_factory=lambda: Path(__file__).parent / "static")
    templates_dir: Path = field(default_factory=lambda: Path(__file__).parent / "templates")

    @property
    def is_production(self) -> bool:
        return self.env == PRODUCTION

    @property
    def console_email(self) -> bool:
        return self.email_backend == "console"

    @property
    def dev_login_code(self) -> str | None:
        """A fixed code that signs in locally without fetching one. Never set in production: it needs the
        console email backend, which load_settings refuses to combine with MAF_ENV=production."""
        if self.is_production or not self.console_email:
            return None
        return DEV_LOGIN_CODE


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _secret(name: str, default: str = "") -> bytes:
    return os.environ.get(name, default).encode()


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Builds Settings from the environment, refusing unsafe combinations."""
    source = os.environ if env is None else env
    backend = source.get("EMAIL_BACKEND", "ses").strip().lower()
    settings = Settings(
        env=source.get("MAF_ENV", "development").strip().lower(),
        database_path=Path(source.get("MAF_DATABASE", "maf.db")),
        label_secret=_secret("LABEL_SECRET", "dev-label-secret"),
        signing_key_path=Path(source["MAF_SIGNING_KEY"]) if source.get("MAF_SIGNING_KEY") else None,
        session_secret=_secret("SESSION_SECRET", "dev-session-secret"),
        maintainer_email=source.get("MAINTAINER_EMAIL", ""),
        email_backend=backend,
        email_from=source.get("MAF_EMAIL_FROM", "maf@maforum.net"),
        aws_region=source.get("AWS_REGION", "us-east-1"),
        azure_email_connection=source.get("AZURE_EMAIL_CONNECTION_STRING", ""),
        name_filter_threshold=float(source.get("NAME_FILTER_THRESHOLD", "0.85")),
        name_filter_enabled=_bool("NAME_FILTER_ENABLED", True),
        spacy_model=source.get("SPACY_MODEL", DEFAULT_SPACY_MODEL),
        base_url=source.get("MAF_BASE_URL", "http://localhost:8000").rstrip("/"),
    )
    if backend not in EMAIL_BACKENDS:
        raise ConfigError(f"EMAIL_BACKEND must be one of {', '.join(sorted(EMAIL_BACKENDS))}")
    if backend == "azure" and not settings.azure_email_connection:
        raise ConfigError("EMAIL_BACKEND=azure needs AZURE_EMAIL_CONNECTION_STRING")
    if settings.is_production and settings.console_email:
        raise ConfigError("EMAIL_BACKEND=console cannot be used with MAF_ENV=production")
    # The dev defaults are public (the repo is open source): production must have its own secrets.
    for name, value in (("LABEL_SECRET", settings.label_secret), ("SESSION_SECRET", settings.session_secret)):
        if settings.is_production and (not value or value.startswith(b"dev-")):
            raise ConfigError(f"{name} must be set to a real secret when MAF_ENV=production")
    # Missing, the model would be downloaded on the first post, which fails on the read-only server.
    if settings.is_production and settings.name_filter_enabled and importlib.util.find_spec(settings.spacy_model) is None:
        raise ConfigError(f"spaCy model {settings.spacy_model} isn't installed; it must be in pyproject.toml")
    return settings
