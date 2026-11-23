"""Privacy: nothing derived from an email is written to disk or logged.

These are hard requirements from SPEC.md. The email is used to send a code, then
forgotten; no table, file or log line may contain it or any hash of it.
"""

import hashlib
import logging
from pathlib import Path

from tests.test_auth import latest_code, sign_in

EMAIL = "very.distinct.student@uni.minerva.edu"
LOCAL = "very.distinct.student"


def _email_forms() -> list[str]:
    forms = {EMAIL, LOCAL, EMAIL.upper(), LOCAL.upper()}
    for salt in ("", "maf", "pepper"):
        forms.add(hashlib.sha256((salt + EMAIL).encode()).hexdigest())
        forms.add(hashlib.sha512((salt + EMAIL).encode()).hexdigest())
    return [f for f in forms if f]


def _dump_database(path: Path) -> str:
    return "".join(f.read_bytes().decode("latin-1") for f in path.parent.glob(path.name + "*") if f.is_file())


def test_no_email_in_the_database(client, app, settings):
    sign_in(client, app, EMAIL)
    client.post("/sign-in/redeem", data=sign_in(client, app, EMAIL), follow_redirects=False)
    dump = _dump_database(settings.database_path)
    for form in _email_forms():
        assert form not in dump, f"{form!r} leaked into the database"


def test_no_email_in_logs(client, app, caplog):
    caplog.set_level(logging.DEBUG)
    sign_in(client, app, EMAIL)
    client.post("/sign-in/redeem", data=sign_in(client, app, EMAIL), follow_redirects=False)
    logged = "\n".join(record.getMessage() for record in caplog.records) + caplog.text
    for form in _email_forms():
        assert form not in logged, f"{form!r} leaked into logs"


def test_no_email_in_disk_files(client, app, settings, tmp_path):
    """Every file the run creates stays clean of the email."""
    sign_in(client, app, EMAIL)
    files = [f for f in tmp_path.rglob("*") if f.is_file()]
    for path in files:
        content = path.read_bytes().decode("latin-1")
        for form in _email_forms():
            assert form not in content, f"{form!r} leaked into {path}"


def test_no_ip_columns_anywhere(app):
    tables = [r["name"] for r in app.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    for table in tables:
        columns = [r["name"].lower() for r in app.conn.execute(f"PRAGMA table_info({table})").fetchall()]
        assert not [c for c in columns if "ip" == c or "ip_" in c or c.endswith("_ip")], table


def test_volatile_state_is_in_memory_only(client, app, settings):
    """Codes, cooldowns and views never reach the database."""
    client.post("/sign-in", data={"email": EMAIL})
    code = latest_code(app)
    dump = _dump_database(settings.database_path)
    assert code not in dump
    tables = {r["name"] for r in app.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert not tables & {"code", "cooldown", "view", "pending_code"}


def test_console_email_is_refused_in_production():
    import pytest

    from maf.settings import ConfigError, load_settings

    with pytest.raises(ConfigError):
        load_settings({"MAF_ENV": "production", "EMAIL_BACKEND": "console"})


def test_access_log_is_off():
    """Uvicorn runs with access_log=False so no IP addresses are logged."""
    import inspect

    from maf import main

    source = inspect.getsource(main.main)
    assert "access_log=False" in source
