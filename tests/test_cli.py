"""MUR-011 — the headless CLI: new / open / run / list over an injected AgentRunner.

The runner is always a MockAgentRunner (+ scripted FakeAgent) — no real `claude`. Covers the
happy path, the run budget, snapshot/restore on failure, and the argument surface.
"""

from __future__ import annotations

import json
from pathlib import Path

from murari.cli import build_parser, main
from murari.config import Config
from murari.runner import MockAgentRunner
from murari.session import create_session, open_session

FIX = Path(__file__).parent / "fixtures" / "contract-v2"
_ALL_ROLES = ("generate", "evaluate", "deepen", "oppose", "mutate", "weave")


def _contracts(*roles: str) -> dict:
    roles = roles or _ALL_ROLES
    return {r: json.loads((FIX / f"{r}.json").read_text(encoding="utf-8")) for r in roles}


def _cfg(tmp_path, runs: int = 6) -> Config:
    return Config(runs=runs, max_turns=15, model="m", home=tmp_path)


# --- parser ---


def test_parser_requires_subcommand():
    import pytest

    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_parser_rejects_unknown_style():
    import pytest

    with pytest.raises(SystemExit):
        build_parser().parse_args(["new", "t", "--style", "bogus"])


# --- new ---


def test_new_creates_and_runs(tmp_path, fake_agent_cls, capsys):
    cfg = _cfg(tmp_path)
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    argv = ["new", "тема сесії", "--name", "heat", "--style", "investigate"]
    rc = main(argv, runner=mock, config=cfg)
    assert rc == 0

    out = capsys.readouterr().out
    assert "created" in out and "document: present" in out
    sessions = list(cfg.sessions_dir.iterdir())
    assert len(sessions) == 1 and "heat" in sessions[0].name
    assert (sessions[0] / "output" / "DOCUMENT.md").exists()


def test_new_defaults_to_investigate(tmp_path, fake_agent_cls, capsys):
    cfg = _cfg(tmp_path)
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    rc = main(["new", "тема"], runner=mock, config=cfg)
    assert rc == 0
    assert "style: investigate" in capsys.readouterr().out


# --- run / open on an existing session ---


def test_run_existing_session(tmp_path, fake_agent_cls, capsys):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема", "topic")
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    rc = main(["run", str(session.path), "--style", "debate"], runner=mock, config=cfg)
    assert rc == 0
    assert open_session(session.path).read_document() is not None


def test_open_prints_state(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "заголовок теми\nдеталі")
    rc = main(["open", str(session.path)], runner=MockAgentRunner({}), config=cfg)
    assert rc == 0
    out = capsys.readouterr().out
    assert "заголовок теми" in out and "ledger: (none yet)" in out


def test_open_nonexistent_returns_1(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    rc = main(["open", str(tmp_path / "nope")], runner=MockAgentRunner({}), config=cfg)
    assert rc == 1
    assert "cannot open session" in capsys.readouterr().err


# --- list ---


def test_list_reports_sessions(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    create_session(cfg, "t", "a", stamp="20260101-090000")
    create_session(cfg, "t", "b", stamp="20260102-090000")
    rc = main(["list"], runner=MockAgentRunner({}), config=cfg)
    assert rc == 0
    lines = capsys.readouterr().out.split()
    assert lines[0].endswith("-b") and lines[1].endswith("-a")  # most recent first


def test_list_empty(tmp_path, capsys):
    rc = main(["list"], runner=MockAgentRunner({}), config=_cfg(tmp_path))
    assert rc == 0 and "no sessions" in capsys.readouterr().out


# --- failure hygiene ---


def test_run_failure_restores_workspace(tmp_path, fake_agent_cls, capsys):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема")
    # only `generate` has a canned contract → the 2nd move (evaluate) raises RunnerError
    mock = MockAgentRunner(_contracts("generate"), on_run=fake_agent_cls())
    rc = main(["run", str(session.path), "--style", "investigate"], runner=mock, config=cfg)

    assert rc == 1
    assert "workspace restored" in capsys.readouterr().err
    assert not session.ledger_file.exists()  # the generate move's ledger was rolled back
