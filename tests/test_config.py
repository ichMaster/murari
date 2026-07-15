"""MUR-006 — config: defaults, env overrides, and the .env loader.

Stdlib only; no network, no paid calls. `os.environ` is fully isolated per test because
`load_dotenv` writes to it directly.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from murari import config as cfg

_KEYS = (
    "MURARI_RUNS",
    "MURARI_MAX_TURNS",
    "MURARI_MODEL",
    "MURARI_HOME",
    "MURARI_RUN_TIMEOUT",
    "MURARI_CHAT_MODEL",
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Snapshot/restore os.environ and point ENV_FILE at nothing so the real repo .env
    never leaks into a test."""
    saved = dict(os.environ)
    for k in _KEYS:
        os.environ.pop(k, None)
    monkeypatch.setattr(cfg, "ENV_FILE", Path("/nonexistent/does-not-exist.env"))
    yield
    os.environ.clear()
    os.environ.update(saved)


def test_defaults():
    c = cfg.load_config()
    assert c.runs == 6
    assert c.max_turns == 15
    assert c.model == "claude-opus-4-8"
    assert c.run_timeout_s == 900
    assert c.chat_model == "claude-haiku-4-5"
    assert c.home == cfg.PROJECT_ROOT / ".murari"
    assert c.sessions_dir == cfg.PROJECT_ROOT / ".murari" / "brainstorm-sessions"


def test_env_overrides(tmp_path):
    os.environ["MURARI_RUNS"] = "3"
    os.environ["MURARI_MAX_TURNS"] = "8"
    os.environ["MURARI_MODEL"] = "claude-sonnet-5"
    os.environ["MURARI_HOME"] = str(tmp_path / "home")
    os.environ["MURARI_RUN_TIMEOUT"] = "1800"
    os.environ["MURARI_CHAT_MODEL"] = "claude-haiku-9"
    c = cfg.load_config()
    assert c.runs == 3
    assert c.max_turns == 8
    assert c.model == "claude-sonnet-5"
    assert c.home == tmp_path / "home"
    assert c.run_timeout_s == 1800
    assert c.chat_model == "claude-haiku-9"


def test_bad_int_falls_back():
    os.environ["MURARI_RUNS"] = "not-a-number"
    assert cfg.load_config().runs == 6


def test_empty_env_uses_default():
    os.environ["MURARI_MODEL"] = ""  # blank must not win over the default
    assert cfg.load_config().model == "claude-opus-4-8"


def test_dotenv_loader(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "MURARI_MODEL=from-dotenv\n# whole-line comment\nMURARI_RUNS=9  # inline\n",
        encoding="utf-8",
    )
    cfg.load_dotenv(env)
    assert os.environ["MURARI_MODEL"] == "from-dotenv"
    assert os.environ["MURARI_RUNS"] == "9"  # inline comment stripped


def test_real_env_var_wins_over_dotenv(tmp_path):
    env = tmp_path / ".env"
    env.write_text("MURARI_MODEL=from-dotenv\n", encoding="utf-8")
    os.environ["MURARI_MODEL"] = "from-real-env"
    cfg.load_dotenv(env)  # setdefault must NOT overwrite an already-set var
    assert os.environ["MURARI_MODEL"] == "from-real-env"
