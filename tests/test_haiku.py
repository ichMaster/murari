"""MUR-012 — the Haiku model seam + session auto-naming (Namer, local fallback).

Everything runs on MockHaikuModel or the no-API local fallback — no key, no SDK, no paid
call (the root conftest strips ANTHROPIC_API_KEY for every test). Also pins the TOPIC.md
format seam: the optional `# <name>` heading above an intact topic body.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from murari.cli import main
from murari.config import Config
from murari.haiku import (
    AnthropicHaikuModel,
    HaikuError,
    HaikuReply,
    MockHaikuModel,
    Namer,
    local_name,
)
from murari.runner import MockAgentRunner
from murari.session import Session, create_session, titled_topic

FIX = Path(__file__).parent / "fixtures" / "contract-v2"
_ALL_ROLES = ("generate", "evaluate", "deepen", "oppose", "mutate", "weave")


def _contracts() -> dict:
    return {r: json.loads((FIX / f"{r}.json").read_text(encoding="utf-8")) for r in _ALL_ROLES}


def _cfg(tmp_path) -> Config:
    return Config(runs=6, max_turns=15, model="m", home=tmp_path)


# --- local_name (the no-API fallback) ---


def test_local_name_uses_first_line():
    assert local_name("Теплові насоси для будинків\n\nдовший опис") == (
        "Теплові насоси для будинків"
    )


def test_local_name_trims_words_and_length():
    long = "одна дві три чотири п'ять шість сім вісім дев'ять десять"
    out = local_name(long)
    assert len(out.split()) <= 8 and len(out) <= 60


def test_local_name_strips_heading_and_punctuation():
    assert local_name("# Чи живе людство в симуляції?") == "Чи живе людство в симуляції"


def test_local_name_empty_topic():
    assert local_name("   \n\n") == "Без назви"


# --- Namer ---


def test_namer_uses_haiku_title():
    mock = MockHaikuModel([HaikuReply(text="«Симуляція як гіпотеза»\nзайвий рядок")])
    assert Namer(mock).name("тема про симуляцію") == "Симуляція як гіпотеза"
    assert len(mock.calls) == 1  # exactly one Messages-API turn
    assert mock.calls[0]["tools"] is None  # the Namer needs no tools


def test_namer_falls_back_on_haiku_error():
    mock = MockHaikuModel([HaikuError("boom")])
    assert Namer(mock).name("тема сесії") == local_name("тема сесії")


def test_namer_falls_back_on_empty_reply():
    mock = MockHaikuModel([HaikuReply(text="   ")])
    assert Namer(mock).name("тема сесії") == local_name("тема сесії")


def test_namer_without_model_is_local():
    assert Namer(None).name("тема сесії") == local_name("тема сесії")


def test_namer_never_raises_without_key(tmp_path):
    # conftest strips ANTHROPIC_API_KEY → the real model raises HaikuError → local fallback
    namer = Namer(AnthropicHaikuModel(_cfg(tmp_path)))
    assert namer.name("тема сесії") == local_name("тема сесії")


def test_real_model_without_key_raises_typed(tmp_path):
    with pytest.raises(HaikuError, match="ANTHROPIC_API_KEY"):
        AnthropicHaikuModel(_cfg(tmp_path)).complete("s", [{"role": "user", "content": "x"}])


# --- TOPIC.md format (contract: heading optional, body intact) ---


def test_titled_topic_roundtrip(tmp_path):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, titled_topic("Гарна назва", "тіло теми\nдругий рядок"))
    assert session.read_title() == "Гарна назва"
    assert "тіло теми\nдругий рядок" in session.read_topic()  # body byte-identical


def test_headingless_topic_has_no_title(tmp_path):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "проста тема без заголовка")
    assert session.read_title() is None
    assert session.read_topic() == "проста тема без заголовка"


def test_read_title_on_missing_topic(tmp_path):
    assert Session(tmp_path / "nope").read_title() is None


# --- CLI wiring: new / list / open ---


def test_new_writes_haiku_title(tmp_path, fake_agent_cls, capsys):
    cfg = _cfg(tmp_path)
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    haiku = MockHaikuModel([HaikuReply(text="Гарна назва")])
    rc = main(["new", "тема сесії"], runner=mock, config=cfg, haiku=haiku)
    assert rc == 0
    assert "— Гарна назва" in capsys.readouterr().out
    (session_dir,) = cfg.sessions_dir.iterdir()
    session = Session(session_dir)
    assert session.read_title() == "Гарна назва"
    assert "тема сесії" in session.read_topic()


def test_new_name_flag_bypasses_haiku(tmp_path, fake_agent_cls):
    cfg = _cfg(tmp_path)
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    haiku = MockHaikuModel([HaikuReply(text="не має бути вжито")])
    rc = main(["new", "тема", "--name", "heat"], runner=mock, config=cfg, haiku=haiku)
    assert rc == 0
    assert haiku.calls == []  # --name → no Haiku call at all
    (session_dir,) = cfg.sessions_dir.iterdir()
    assert Session(session_dir).read_title() == "heat"


def test_new_without_key_uses_local_fallback(tmp_path, fake_agent_cls):
    cfg = _cfg(tmp_path)
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    rc = main(["new", "тема про симуляцію"], runner=mock, config=cfg)  # default real model
    assert rc == 0
    (session_dir,) = cfg.sessions_dir.iterdir()
    assert Session(session_dir).read_title() == local_name("тема про симуляцію")


def test_list_renders_titles_and_plain_dirs(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    create_session(cfg, titled_topic("Названа сесія", "тема"), stamp="20260101-000001")
    create_session(cfg, "тема без назви", stamp="20260101-000002")  # pre-v0.2 layout
    rc = main(["list"], runner=MockAgentRunner({}), config=cfg, haiku=MockHaikuModel())
    assert rc == 0
    out = capsys.readouterr().out.splitlines()
    assert any(ln.endswith("— Названа сесія") for ln in out)
    assert any(ln == "session-20260101-000002" for ln in out)


def test_open_prints_title_and_topic_body(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, titled_topic("Гарна назва", "тіло теми"))
    rc = main(
        ["open", str(session.path)],
        runner=MockAgentRunner({}),
        config=cfg,
        haiku=MockHaikuModel(),
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "name: Гарна назва" in out
    assert "topic: тіло теми" in out  # the body, not the heading
