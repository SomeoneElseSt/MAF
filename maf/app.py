"""Application context: everything a request needs, built once at startup."""

import sqlite3
import threading
from dataclasses import dataclass, field

from . import db
from .blind import PrivateKey, PublicKey, load_key
from .email import Emailer
from .labels import Labeler
from .live import Notifier
from .memory import Memory
from .namefilter import NameFilter
from .sessions import Sessions
from .settings import Settings
from .usage import UsageLog


@dataclass
class App:
    settings: Settings
    memory: Memory
    sessions: Sessions
    labeler: Labeler
    name_filter: NameFilter
    emailer: Emailer
    signing_key: PrivateKey
    live: Notifier = field(default_factory=Notifier)
    usage: UsageLog = field(default_factory=lambda: UsageLog(None))
    pusher: object = None
    _local: threading.local = field(default_factory=threading.local)
    templates: object = None
    _: tuple = field(default_factory=tuple)

    @property
    def conn(self) -> sqlite3.Connection:
        """This thread's own database connection.

        Pages run side by side in worker threads, and one SQLite connection can't be shared between
        threads safely. With WAL, separate connections read and write alongside each other.
        """
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = db.connect(self.settings.database_path)
            self._local.conn = conn
        return conn

    @property
    def public_key(self) -> PublicKey:
        return self.signing_key.public


def build_app(settings: Settings) -> App:
    signing_key = load_signing_key(settings)
    app = App(
        settings=settings,
        memory=Memory(),
        sessions=Sessions(settings),
        labeler=Labeler(settings.label_secret),
        name_filter=NameFilter(settings),
        emailer=Emailer(settings),
        signing_key=signing_key,
        usage=UsageLog(settings.usage_log_path),
        pusher=_pusher(settings),
    )
    db.migrate(app.conn)
    return app


def _pusher(settings: Settings):
    from .push import Pusher  # push.py uses web.py, which imports this module

    return Pusher(settings)


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
