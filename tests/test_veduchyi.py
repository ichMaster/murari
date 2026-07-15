"""MUR-013 — Ведучий: the facilitation loop, the single-tool boundary, and the dispatch.

Mock Haiku + MockAgentRunner/FakeAgent everywhere — no paid calls. Pins the Tier-1 seam:
exactly one tool (`run_brainstorm`, accepted signature incl. depth), args validated as data,
invalid calls refused without a run, budgets enforced before spending.
"""

from __future__ import annotations

import json
from pathlib import Path

from murari.config import Config
from murari.contract import MUTATION_TYPES, ROLES
from murari.engine import DEPTHS
from murari.haiku import HaikuReply, MockHaikuModel, ToolCall
from murari.runner import MockAgentRunner
from murari.session import create_session
from murari.veduchyi import (
    FACILITATION_SYSTEM,
    RUN_BRAINSTORM_TOOL,
    Dispatcher,
    Refusal,
    Veduchyi,
    result_payload,
)

FIX = Path(__file__).parent / "fixtures" / "contract-v2"
_ALL_ROLES = ("generate", "evaluate", "deepen", "oppose", "mutate", "weave")


def _contracts() -> dict:
    return {r: json.loads((FIX / f"{r}.json").read_text(encoding="utf-8")) for r in _ALL_ROLES}


def _cfg(tmp_path, runs: int = 6) -> Config:
    return Config(runs=runs, max_turns=15, model="m", home=tmp_path)


def _call(**args) -> ToolCall:
    return ToolCall(name="run_brainstorm", arguments=args, id="t1")


def _setup(tmp_path, fake_agent_cls, runs: int = 6):
    cfg = _cfg(tmp_path, runs)
    session = create_session(cfg, "тема сесії")
    runner = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    return cfg, session, runner


# --- the single-tool boundary (contract) ---


def test_tool_schema_matches_accepted_signature():
    schema = RUN_BRAINSTORM_TOOL["input_schema"]
    assert RUN_BRAINSTORM_TOOL["name"] == "run_brainstorm"
    assert set(schema["properties"]) == {
        "seed",
        "role",
        "target_idea",
        "mutation_type",
        "style_step",
        "depth",
    }
    assert schema["required"] == ["seed", "role"]
    assert schema["properties"]["role"]["enum"] == sorted(ROLES)
    assert schema["properties"]["mutation_type"]["enum"] == sorted(MUTATION_TYPES)
    assert schema["properties"]["depth"]["enum"] == list(DEPTHS)


def test_loop_registers_exactly_one_tool(tmp_path, fake_agent_cls):
    cfg, session, runner = _setup(tmp_path, fake_agent_cls)
    haiku = MockHaikuModel([HaikuReply(text="Вітаю! Про що думаємо?")])
    v = Veduchyi(cfg, haiku, runner, session)
    assert v.turn("привіт") == "Вітаю! Про що думаємо?"
    (call,) = haiku.calls
    assert call["tools"] == [RUN_BRAINSTORM_TOOL]  # exactly one tool, nothing else
    assert call["system"] == FACILITATION_SYSTEM


def test_foreign_tool_is_refused_without_side_effect(tmp_path, fake_agent_cls):
    cfg, session, runner = _setup(tmp_path, fake_agent_cls)
    haiku = MockHaikuModel(
        [
            HaikuReply(tool_call=ToolCall(name="write_file", arguments={}, id="x")),
            HaikuReply(text="вибач, такого інструмента немає"),
        ]
    )
    v = Veduchyi(cfg, haiku, runner, session)
    assert v.turn("запиши файл") == "вибач, такого інструмента немає"
    assert runner.calls == []  # no run was launched
    tool_result = haiku.calls[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert "невідомий інструмент" in tool_result["content"]


# --- dispatch validation (each refusal launches nothing) ---


def test_dispatch_refuses_bad_args(tmp_path, fake_agent_cls):
    cfg, session, runner = _setup(tmp_path, fake_agent_cls)
    d = Dispatcher(cfg, runner)
    bad_calls = [
        _call(seed="s", role="dictator"),  # unknown role
        _call(seed="s", role="deepen", target_idea="H99"),  # unknown H-id (empty ledger)
        _call(seed="s", role="mutate", mutation_type="explode"),  # unknown mutation type
        _call(seed="s", role="generate", depth="huge"),  # unknown depth
        _call(seed="s", role="generate", style_step="bogus[1]"),  # unknown style
        _call(seed="  ", role="generate"),  # empty seed
        _call(seed="s", role="generate", extra="?"),  # unknown argument
    ]
    for call in bad_calls:
        outcome = d.dispatch(session, call)
        assert isinstance(outcome, Refusal), call.arguments
    assert runner.calls == []


def test_dispatch_single_move_reaches_engine(tmp_path, fake_agent_cls):
    cfg, session, runner = _setup(tmp_path, fake_agent_cls)
    res = Dispatcher(cfg, runner).dispatch(session, _call(seed="контекст ходу", role="generate"))
    assert not isinstance(res, Refusal)
    assert [m.move for m in res.moves] == ["generate"]
    assert res.depth == "custom" and res.stopped == "completed"
    (req,) = runner.calls
    assert req.role == "generate"
    assert req.seed_text == "контекст ходу"  # the seed rides the kickoff
    assert session.read_ledger() is not None  # the move landed in the workspace


def test_dispatch_depth_runs_the_style_sequence(tmp_path, fake_agent_cls):
    cfg, session, runner = _setup(tmp_path, fake_agent_cls)
    res = Dispatcher(cfg, runner).dispatch(
        session, _call(seed="s", role="generate", depth="brief", style_step="investigate[0]")
    )
    assert not isinstance(res, Refusal)
    assert [m.move for m in res.moves] == ["generate", "evaluate", "weave"]
    assert session.read_document() is not None  # brief still ends in a document


def test_dispatch_honors_mutation_override_and_target(tmp_path, fake_agent_cls):
    cfg, session, runner = _setup(tmp_path, fake_agent_cls)
    d = Dispatcher(cfg, runner)
    first = d.dispatch(session, _call(seed="s", role="generate"))  # H1..H3 appear
    assert not isinstance(first, Refusal)
    res = d.dispatch(
        session, _call(seed="s", role="mutate", target_idea="H1", mutation_type="invert")
    )
    assert not isinstance(res, Refusal)
    req = runner.calls[-1]
    assert req.role == "mutate" and req.target_idea == "H1"
    assert req.mutation_type == "invert"  # the explicit type, not the seeded pick


def test_dispatch_refuses_beyond_budget(tmp_path, fake_agent_cls):
    cfg, session, runner = _setup(tmp_path, fake_agent_cls, runs=2)
    outcome = Dispatcher(cfg, runner).dispatch(
        session,
        _call(seed="s", role="generate", depth="brief"),  # 3 moves > 2
    )
    assert isinstance(outcome, Refusal) and "бюджет" in outcome.reason
    assert runner.calls == []  # refused before spending


# --- the full turn: user → Haiku → dispatch → engine → reply ---


def test_turn_dispatches_and_replies(tmp_path, fake_agent_cls):
    cfg, session, runner = _setup(tmp_path, fake_agent_cls)
    haiku = MockHaikuModel(
        [
            HaikuReply(
                text="Запускаю Фантазера", tool_call=_call(seed="про тему", role="generate")
            ),
            HaikuReply(text="Готово: у ledger три нові ідеї"),
        ]
    )
    v = Veduchyi(cfg, haiku, runner, session)
    assert v.turn("накидай ідей") == "Готово: у ledger три нові ідеї"
    assert [req.role for req in runner.calls] == ["generate"]
    # the tool round is recorded in Messages-API shape, result as quoted data
    tool_result = haiku.calls[1]["messages"][-1]["content"][0]
    payload = json.loads(tool_result["content"])
    assert payload["moves"] == [
        {"move": "generate", "target": None, "mutation_type": None, "dry": False}
    ]
    assert len(v.history) == 4  # user, assistant tool_use, user tool_result, assistant text


def test_turn_allows_one_tool_round_per_reply(tmp_path, fake_agent_cls):
    cfg, session, runner = _setup(tmp_path, fake_agent_cls)
    haiku = MockHaikuModel(
        [
            HaikuReply(tool_call=_call(seed="s", role="generate")),
            HaikuReply(tool_call=_call(seed="s", role="generate")),  # a second ask — refused
            HaikuReply(text="зупиняюсь"),
        ]
    )
    v = Veduchyi(cfg, haiku, runner, session)
    assert v.turn("ще і ще") == "зупиняюсь"
    assert len(runner.calls) == 1  # only the first round dispatched
    second_result = haiku.calls[2]["messages"][-1]["content"][0]["content"]
    assert "ліміт" in second_result


def test_result_payload_is_plain_data(tmp_path, fake_agent_cls):
    cfg, session, runner = _setup(tmp_path, fake_agent_cls)
    res = Dispatcher(cfg, runner).dispatch(session, _call(seed="s", role="generate"))
    payload = result_payload(res)
    assert json.dumps(payload)  # serializable, quoted material for the tool_result
    assert payload["stopped"] == "completed" and payload["error"] is None
