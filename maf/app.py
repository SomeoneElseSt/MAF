"""Application context: everything a request needs, built once at startup."""

import sqlite3
from dataclasses import dataclass, field

from . import db
from .blind import PrivateKey, PublicKey, load_key
from .email import Emailer
from .labels import Labeler
from .memory import Memory
from .namefilter import NameFilter
from .sessions import Sessions
from .settings import Settings


@dataclass
class App:
    settings: Settings
    conn: sqlite3.Connection
    memory: Memory
    sessions: Sessions
    labeler: Labeler
    name_filter: NameFilter
    emailer: Emailer
    signing_key: PrivateKey
    templates: object = None
    _: tuple = field(default_factory=tuple)

    @property
    def public_key(self) -> PublicKey:
        return self.signing_key.public


def build_app(settings: Settings) -> App:
    conn = db.connect(settings.database_path)
    db.migrate(conn)
    signing_key = load_signing_key(settings)
    return App(
        settings=settings,
        conn=conn,
        memory=Memory(),
        sessions=Sessions(settings),
        labeler=Labeler(settings.label_secret),
        name_filter=NameFilter(settings),
        emailer=Emailer(settings),
        signing_key=signing_key,
    )


def load_signing_key(settings: Settings):
    """Loads the RSA key, generating one for local development if no path is set."""
    from pathlib import Path

    from .blind import generate_key

    if settings.signing_key_path is not None:
        return load_key(settings.signing_key_path)
    if settings.is_production:
        raise ValueError("MAF_SIGNING_KEY is required in production")
    dev_path = Path(f"{settings.database_path}.key")
    if not dev_path.exists():
        generate_key(dev_path)
    return load_key(dev_path)
