"""The maintainer CLI finds the site's database, and refuses to make an empty one."""

import maf.cli as cli


def test_settings_from_the_site_env_file_fill_in_what_is_missing(monkeypatch, tmp_path):
    site_db = tmp_path / "site.db"
    site_db.touch()
    env_file = tmp_path / "env"
    env_file.write_text(f'# comment\nMAF_DATABASE="{site_db}"\nLABEL_SECRET=from-the-file\n')
    monkeypatch.setattr(cli, "SITE_ENV", env_file)
    monkeypatch.delenv("MAF_DATABASE", raising=False)
    monkeypatch.setenv("LABEL_SECRET", "already-set")
    cli._load_env()
    import os
    assert os.environ["MAF_DATABASE"] == str(site_db)
    # Never overrides what the shell already has.
    assert os.environ["LABEL_SECRET"] == "already-set"
    monkeypatch.delenv("MAF_DATABASE")


def test_a_missing_database_is_refused_instead_of_created(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "SITE_ENV", tmp_path / "no-env")
    missing = tmp_path / "nothing.db"
    monkeypatch.setenv("MAF_DATABASE", str(missing))
    try:
        cli._connect()
    except SystemExit as stop:
        assert "No database at" in str(stop)
    else:
        raise AssertionError("the CLI opened a missing database")
    assert not missing.exists()
