"""MUR-010 — session lifecycle: create, open-and-continue, listing, failure hygiene.

Everything runs under a tmp MURARI_HOME; deterministic timestamps via the `stamp` arg.
"""

from __future__ import annotations

import pytest

from murari.config import Config
from murari.session import (
    SessionError,
    create_session,
    list_sessions,
    open_session,
    restore_state,
    slugify,
    snapshot_state,
)

_LEDGER_V2 = (
    "# LEDGER\n\n## Гіпотези\n- [H1][confirmed] теза — джерело: https://e.com/a\n\n"
    "## Прогони\n- 1: evaluate(агент) → H1 confirmed\n\n## Сухі прогони поспіль: 0\n"
)


def _cfg(tmp_path) -> Config:
    return Config(runs=6, max_turns=15, model="m", home=tmp_path)


# --- slugify ---


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Heat Pumps", "heat-pumps"),
        ("silicon  CPUs!", "silicon-cpus"),
        ("Тема українською", ""),  # non-ASCII → empty (falls back to timestamp)
    ],
)
def test_slugify(name, expected):
    assert slugify(name) == expected


# --- create ---


def test_create_layout(tmp_path):
    s = create_session(_cfg(tmp_path), "тема сесії", "heat pumps", stamp="20260101-120000")
    assert s.path.name == "session-20260101-120000-heat-pumps"
    assert s.topic_file.read_text(encoding="utf-8") == "тема сесії"
    assert s.input_dir.is_dir() and s.artifacts_dir.is_dir()
    assert not s.ledger_file.exists()  # agent creates it on first run


def test_create_no_name_is_timestamp_only(tmp_path):
    s = create_session(_cfg(tmp_path), "t", stamp="20260101-120000")
    assert s.path.name == "session-20260101-120000"


def test_create_collision_safe(tmp_path):
    cfg = _cfg(tmp_path)
    a = create_session(cfg, "t", "x", stamp="20260101-120000")
    b = create_session(cfg, "t", "x", stamp="20260101-120000")
    assert a.path.name == "session-20260101-120000-x"
    assert b.path.name == "session-20260101-120000-x-2"


# --- open-and-continue ---


def test_open_and_continue(tmp_path):
    s = create_session(_cfg(tmp_path), "t", "x", stamp="20260101-120000")
    s.ledger_file.write_text(_LEDGER_V2, encoding="utf-8")
    s.document_file.write_text("# Документ\nтекст\n", encoding="utf-8")

    reopened = open_session(s.path)
    led = reopened.read_ledger()
    assert led is not None and led.by_id("H1").status == "confirmed"
    assert reopened.read_document().startswith("# Документ")


def test_open_fresh_session_has_no_ledger(tmp_path):
    s = create_session(_cfg(tmp_path), "t", stamp="20260101-120000")
    assert open_session(s.path).read_ledger() is None


def test_open_malformed_dir_raises(tmp_path):
    (tmp_path / "not-a-session").mkdir()
    with pytest.raises(SessionError):
        open_session(tmp_path / "not-a-session")


# --- listing ---


def test_list_sessions_most_recent_first(tmp_path):
    cfg = _cfg(tmp_path)
    create_session(cfg, "t", "a", stamp="20260101-090000")
    create_session(cfg, "t", "b", stamp="20260102-090000")
    create_session(cfg, "t", "c", stamp="20260101-190000")
    names = [s.path.name for s in list_sessions(cfg)]
    assert names == [
        "session-20260102-090000-b",
        "session-20260101-190000-c",
        "session-20260101-090000-a",
    ]


def test_list_sessions_empty(tmp_path):
    assert list_sessions(_cfg(tmp_path)) == []


# --- failure hygiene ---


def test_snapshot_restore_rolls_back_state(tmp_path):
    s = create_session(_cfg(tmp_path), "t", stamp="20260101-120000")
    s.ledger_file.write_text(_LEDGER_V2, encoding="utf-8")  # LEDGER exists; DOCUMENT does not

    snap = snapshot_state(s)

    # simulate a failed run: corrupt the ledger and create a stray document
    s.ledger_file.write_text("# LEDGER\ncorrupted\n", encoding="utf-8")
    s.document_file.write_text("half-written\n", encoding="utf-8")

    restore_state(s, snap)

    assert s.ledger_file.read_text(encoding="utf-8") == _LEDGER_V2  # restored
    assert not s.document_file.exists()  # was absent before → removed
