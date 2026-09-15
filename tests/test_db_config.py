"""Regression test for the removed CONTA_DB_PATH silent fallback (db.py).

Context: db.py used to fall back to "./conta.db" when CONTA_DB_PATH was
unset. An ad-hoc script that imported conta.app.db without setting it wrote
two garbage rows into the real production database (2026-09-15 incident).
db.py now raises RuntimeError instead of falling back to any default.

This test forces a genuine re-import of conta.app.db with CONTA_DB_PATH
absent from the environment. python-dotenv's load_dotenv() locates .env via
call-stack introspection (not CWD), so it would otherwise still find this
project's real .env from db.py's own file location regardless of the test's
working directory -- silently re-supplying the real path and defeating the
point of this test. The one thing that actually changed in this phase is
db.py's Python-level fallback, so dotenv.load_dotenv is monkeypatched to a
no-op at its source (not on db_module's local alias, which reload() would
just re-bind back to the real function via db.py's own `from dotenv import
load_dotenv` line) to isolate exactly that.
"""

import importlib

import dotenv

import conta.app.db as db_module


def test_missing_conta_db_path_raises_instead_of_falling_back(monkeypatch, tmp_path):
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.delenv("CONTA_DB_PATH", raising=False)

    try:
        import pytest

        with pytest.raises(RuntimeError, match="CONTA_DB_PATH"):
            importlib.reload(db_module)
    finally:
        # Restore a working module state for every test that runs after this
        # one: reload() executes db.py's top level again, and it fails before
        # reassigning `engine`, so the previous (guard-path) engine set by
        # conftest.py survives untouched -- but DB_PATH itself was still set
        # to None mid-failure, so put the module back in a fully consistent
        # state by reloading it again with a valid path in scope.
        monkeypatch.undo()
        importlib.reload(db_module)


def test_reload_with_conta_db_path_set_succeeds(monkeypatch, tmp_path):
    """Sanity check for the test above: reload() with a valid CONTA_DB_PATH
    does NOT raise, confirming the RuntimeError in the other test is caused
    specifically by the missing env var, not by reload() itself."""
    db_path = tmp_path / "some_isolated_file.db"
    monkeypatch.setenv("CONTA_DB_PATH", str(db_path))

    try:
        importlib.reload(db_module)
        assert str(db_module.engine.url.database) == str(db_path)
    finally:
        # Leave the module pointing at a live path again for any test that
        # runs after this one without going through the `db` fixture.
        monkeypatch.undo()
        importlib.reload(db_module)
