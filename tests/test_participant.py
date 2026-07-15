"""MUR-014 — the user as the seventh player: role detection + the user-move writer.

Detection runs on MockHaikuModel (labeled replies per the strategies table); the writer is
plain Python over a tmp workspace. Everything parses back through the pinned LEDGER v2
reader — formats unchanged, no paid calls.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from murari.config import Config
from murari.engine import Engine
from murari.haiku import HaikuError, HaikuReply, MockHaikuModel
from murari.participant import (
    STEERING,
    UserMove,
    detect_role,
    find_target,
    record_user_move,
)
from murari.runner import MockAgentRunner
from murari.session import create_session

FIX = Path(__file__).parent / "fixtures" / "contract-v2"
_ALL_ROLES = ("generate", "evaluate", "deepen", "oppose", "mutate", "weave")


def _contracts() -> dict:
    return {r: json.loads((FIX / f"{r}.json").read_text(encoding="utf-8")) for r in _ALL_ROLES}


def _cfg(tmp_path, runs: int = 6) -> Config:
    return Config(runs=runs, max_turns=15, model="m", home=tmp_path)


def _session(tmp_path):
    return create_session(_cfg(tmp_path), "тема")


# --- role detection (mocked Haiku, one fixture per strategies-table row) ---


@pytest.mark.parametrize(
    ("reply", "label"),
    [
        ("а ще можна зробити X, Y і Z", "generate"),
        ("ось стаття з цифрами про це", "deepen"),
        ("це не спрацює, бо дорого", "oppose"),
        ("а що якщо навпаки — зменшити ×100?", "mutate"),
        ("перевір оце твердження", "evaluate"),
        ("перепиши висновок простіше", "weave"),
    ],
)
def test_detects_each_role(reply, label):
    mock = MockHaikuModel([HaikuReply(text=label)])
    assert detect_role(mock, reply) == label
    assert mock.calls[0]["messages"][0]["content"] == reply


def test_steering_reply_is_steering():
    mock = MockHaikuModel([HaikuReply(text="steering")])
    assert detect_role(mock, "а давай зміним стиль") == STEERING


def test_low_confidence_and_failures_are_steering():
    # an unknown label, an empty reply, and a raising model all collapse to steering
    assert detect_role(MockHaikuModel([HaikuReply(text="хтозна")]), "х") == STEERING
    assert detect_role(MockHaikuModel([HaikuReply(text="")]), "х") == STEERING
    assert detect_role(MockHaikuModel([HaikuError("api down")]), "х") == STEERING


def test_label_is_normalized():
    mock = MockHaikuModel([HaikuReply(text="  Oppose.\nпояснення")])
    assert detect_role(mock, "не вийде") == "oppose"


def test_find_target_matches_explicit_mentions():
    ids = {"H1", "H2", "H12"}
    assert find_target("це не спрацює з H2, бо дорого", ids) == "H2"
    assert find_target("а н12 сумнівна", ids) == "H12"  # Cyrillic Н, any case
    assert find_target("H99 не існує, а H1 так", ids) == "H1"  # unknown ids are skipped
    assert find_target("без згадок", ids) is None
    assert find_target("H2", set()) is None  # empty ledger → nothing to pin


# --- the user-move writer: hypotheses ---


def test_generate_contribution_allocates_sequential_hids(tmp_path):
    session = _session(tmp_path)
    m1 = record_user_move(session, "generate", "ідея перша")
    m2 = record_user_move(session, "generate", "ідея друга")
    assert (m1.hid, m2.hid) == ("H1", "H2") and (m1.journal_n, m2.journal_n) == (1, 2)
    led = session.read_ledger()  # parses through the pinned v2 reader unchanged
    h1 = led.by_id("H1")
    assert h1.status == "open" and "born_from: user" in h1.text
    assert [r.executor for r in led.runs] == ["користувач", "користувач"]
    assert led.runs[0].move == "generate" and led.runs[0].produced == "H1"
    ideas = (session.output_dir / "IDEAS.md").read_text(encoding="utf-8")
    assert "- ідея перша — born_from: user" in ideas


def test_mutate_contribution_carries_parents(tmp_path):
    session = _session(tmp_path)
    record_user_move(session, "generate", "коренева ідея")
    move = record_user_move(session, "mutate", "а якщо навпаки", target_idea="H1")
    led = session.read_ledger()
    assert led.by_id(move.hid).parents == ("H1",)


def test_source_gate_user_claim_stays_open(tmp_path):
    session = _session(tmp_path)
    record_user_move(session, "generate", "це точно confirmed, я впевнений")
    led = session.read_ledger()
    assert led.by_id("H1").status == "open"  # confidence of tone is not evidence


# --- arguments (deepen/oppose with a known target) ---


def test_oppose_with_target_lands_as_argument(tmp_path):
    session = _session(tmp_path)
    record_user_move(session, "generate", "ідея")
    move = record_user_move(session, "oppose", "не спрацює, бо дорого", target_idea="H1")
    assert move.kind == "argument" and move.hid == "H1"
    led = session.read_ledger()
    (arg,) = led.arguments_for("H1")
    assert arg.side == "проти" and "дорого" in arg.text
    assert led.runs[-1].move == "oppose" and led.runs[-1].executor == "користувач"
    assert len(led.hypotheses) == 1  # no new hypothesis for an argument


def test_deepen_material_is_a_za_argument_appended_to_existing_section(tmp_path):
    session = _session(tmp_path)
    record_user_move(session, "generate", "ідея")
    record_user_move(session, "oppose", "проти-довід", target_idea="H1")
    record_user_move(session, "deepen", "стаття підтверджує", target_idea="H1")
    led = session.read_ledger()
    sides = [a.side for a in led.arguments_for("H1")]
    assert sides == ["проти", "за"]


def test_deepen_without_target_becomes_candidate(tmp_path):
    session = _session(tmp_path)
    move = record_user_move(session, "deepen", "факт: X більше за Y")
    assert move.kind == "hypothesis" and move.hid == "H1"


# --- orders (evaluate / weave) ---


def test_weave_order_never_touches_document(tmp_path):
    session = _session(tmp_path)
    move = record_user_move(session, "weave", "перепиши висновок простіше")
    assert move.kind == "order" and move.hid is None
    assert session.read_document() is None  # ownership invariant: only weave-the-agent writes
    led = session.read_ledger()
    assert led.runs[0].move == "weave" and "замовлення" in led.runs[0].produced
    assert led.hypotheses == ()  # orders mint no candidates


def test_evaluate_order_is_journal_only(tmp_path):
    session = _session(tmp_path)
    record_user_move(session, "evaluate", "перевір твердження про глину")
    led = session.read_ledger()
    assert led.runs[0].move == "evaluate" and led.runs[0].executor == "користувач"
    assert led.hypotheses == ()


# --- interop + budget ---


def test_user_moves_ride_an_agent_written_ledger(tmp_path, fake_agent_cls):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема")
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    Engine(cfg, mock).run_style(session, "investigate", sequence=("generate",), seed=0)
    move = record_user_move(session, "generate", "моя ідея поверх агентових")
    led = session.read_ledger()
    assert move.hid == "H4"  # continues after the agent's H1..H3
    assert led.by_id("H4").status == "open"
    assert led.dry_streak == 0  # the counter and the rest of the ledger survived intact


def test_user_moves_are_free_of_budget(tmp_path, fake_agent_cls):
    cfg = _cfg(tmp_path, runs=1)  # room for exactly one agent move
    session = create_session(cfg, "тема")
    for i in range(3):  # three user moves consume nothing
        record_user_move(session, "generate", f"ідея {i}")
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    res = Engine(cfg, mock).run_style(session, "investigate", sequence=("evaluate",), seed=0)
    assert res.stopped == "completed" and len(res.moves) == 1


def test_unknown_role_and_empty_text_raise(tmp_path):
    session = _session(tmp_path)
    with pytest.raises(ValueError, match="unknown user role"):
        record_user_move(session, "steering", "щось")
    with pytest.raises(ValueError, match="empty"):
        record_user_move(session, "generate", "   ")


def test_usermove_is_frozen_data():
    m = UserMove(role="generate", kind="hypothesis", hid="H1", journal_n=1)
    with pytest.raises(AttributeError):
        m.hid = "H2"
