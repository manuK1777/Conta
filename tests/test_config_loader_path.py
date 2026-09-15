"""Regression test for config/loader.py resolving rules.yml relative to its
own file location, not the process's current working directory.

Context (2026-09-15): RULES_PATH defaulted to the relative string
"./config/rules.yml", which only worked when `conta` happened to be run from
the repo root. The installed `conta` command run from any other directory
crashed at import time with FileNotFoundError, since models.py imports this
module at module load -- breaking both `conta m130` (and every other CLI
command) and `conta tui` for real daily use outside the repo root. Confirmed
manually with the actual `conta` entry point (not just this module in
isolation) from /tmp with a fully clean environment (env -i), for both the
CLI and TUI, before and after the fix.

The CLI/TUI entry-point tests below spawn a genuinely fresh subprocess (not
importlib.reload()) run from a different cwd -- the most faithful
reproduction of how the user actually hit this, and it sidesteps reloading
models.py in-process, which would re-register its SQLModel table classes
against the same shared metadata and conflict with the already-imported
originals other tests in this session depend on.

Gap this exposed in the existing suite: every prior test ran with an
unexamined assumption that pytest's rootdir *is* the repo root (true for the
normal `pytest` invocation used throughout this project), so nothing here
would have caught a CWD-dependent bug like this one. These are the first
tests that explicitly do NOT make that assumption.
"""

import importlib
import os
import subprocess
import sys

import config.loader as loader_module


def test_loader_resolves_rules_yml_from_a_different_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv("CONTA_RULES_PATH", raising=False)
    monkeypatch.chdir(tmp_path)  # tmp_path has no rules.yml at all

    try:
        importlib.reload(loader_module)  # must not raise FileNotFoundError
        assert loader_module.IVA_GENERAL is not None
        assert loader_module.IVA_TIPOS["general"] == loader_module.IVA_GENERAL
    finally:
        monkeypatch.undo()
        importlib.reload(loader_module)  # restore normal state for later tests


def test_loader_still_honors_conta_rules_path_override(monkeypatch, tmp_path):
    """The env var override itself is untouched by this fix -- only the
    default/fallback changed. A custom rules.yml elsewhere must still win."""
    custom_rules = tmp_path / "custom_rules.yml"
    custom_rules.write_text(
        "iva_tipos:\n"
        "  general: 19.0\n"
        "  reducido: 9.0\n"
        "  superreducido: 3.0\n"
        "irpf_retenciones_por_actividad:\n"
        "  musica: 7.0\n"
        "  programacion: 0.0\n"
        "modelo130:\n"
        "  porcentaje_pago_fraccionado: 20.0\n"
        "redondeo:\n"
        "  decimales_visualizacion: 2\n"
    )
    monkeypatch.setenv("CONTA_RULES_PATH", str(custom_rules))

    try:
        importlib.reload(loader_module)
        assert loader_module.IVA_GENERAL == loader_module.Decimal("19.00")
    finally:
        monkeypatch.undo()
        importlib.reload(loader_module)


def _run_conta(args: list[str], cwd, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("CONTA_RULES_PATH", None)  # exercise the default resolution, not an override
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", "from conta.app.cli import app; app()", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_cli_entry_point_works_from_a_different_cwd(tmp_path):
    """Reproduces the actual reported crash through the real import chain a
    user hits (cli.py -> models.py -> config.loader) via a genuinely fresh
    process, not just config.loader in isolation -- don't assume fixing the
    loader covers the entry point without checking, per the bug report."""
    isolated_db = tmp_path / "isolated.db"

    init_result = _run_conta(["init"], cwd=tmp_path, extra_env={"CONTA_DB_PATH": str(isolated_db)})
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    m130_result = _run_conta(
        ["m130", "2025Q1"], cwd=tmp_path, extra_env={"CONTA_DB_PATH": str(isolated_db)}
    )
    assert m130_result.returncode == 0, m130_result.stdout + m130_result.stderr
    assert "FileNotFoundError" not in m130_result.stderr


def test_tui_entry_point_imports_from_a_different_cwd(tmp_path):
    """Same failure point (models.py -> config.loader), reached via the TUI's
    own import chain (tui/app.py -> screens/*.py -> ...models) instead of
    cli.py's -- checked separately per the bug report's explicit instruction
    not to assume one fix covers both entry points."""
    isolated_db = tmp_path / "isolated_tui.db"
    env = os.environ.copy()
    env.pop("CONTA_RULES_PATH", None)
    env["CONTA_DB_PATH"] = str(isolated_db)

    result = subprocess.run(
        [sys.executable, "-c", "from conta.app.tui.app import ContaApp"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FileNotFoundError" not in result.stderr
