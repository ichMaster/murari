"""MUR-017 (revised 2026-07-15) — the chat REPL: commands, the /go-only trigger policy,
and the phase DoD as an integration script. Mock Haiku + MockAgentRunner/FakeAgent — no
paid calls anywhere.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from murari.chat import ChatSession, run_repl
from murari.cli import main
from murari.config import Config
from murari.haiku import HaikuReply, MockHaikuModel
from murari.runner import MockAgentRunner
from murari.session import Session, create_session
from murari.veduchyi import RUN_BRAINSTORM_TOOL

FIX = Path(__file__).parent / "fixtures" / "contract-v2"
_ALL_ROLES = ("generate", "evaluate", "deepen", "oppose", "mutate", "weave")


def _contracts() -> dict:
    return {r: json.loads((FIX / f"{r}.json").read_text(encoding="utf-8")) for r in _ALL_ROLES}


def _cfg(tmp_path, runs: int = 6) -> Config:
    return Config(runs=runs, max_turns=15, model="m", home=tmp_path)


def _chat(tmp_path, fake_agent_cls, replies, *, style="investigate", runs=6):
    cfg = _cfg(tmp_path, runs)
    session = create_session(cfg, "тема сесії")
    runner = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    model = MockHaikuModel(replies)
    chat = ChatSession(cfg, session, runner, model, style=style)
    return chat, session, runner, model


# --- commands ---


def test_style_command_shows_sets_and_rejects(tmp_path, fake_agent_cls):
    chat, *_ = _chat(tmp_path, fake_agent_cls, [])
    assert chat.turn("/style") == "стиль: investigate"
    assert chat.turn("/style debate") == "стиль тепер debate"
    assert chat.style == "debate"
    assert "unknown style" in chat.turn("/style bogus")


def test_unknown_command_prints_help(tmp_path, fake_agent_cls):
    chat, *_ = _chat(tmp_path, fake_agent_cls, [])
    assert "/style" in chat.turn("/wat") and "/go" in chat.turn("/wat")


# --- trigger policy (revised): launch ONLY via /go ---


def test_classified_reply_records_and_plans_without_launching(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(tmp_path, fake_agent_cls, [HaikuReply(text="generate")])
    out = chat.turn("а ще можна використати X")
    assert runner.calls == []  # nothing launched — /go is the only trigger
    assert "записано: твій хід Фантазера" in out and "/go" in out
    led = session.read_ledger()  # the user's move is already durable state
    assert led.by_id("H1").status == "open" and led.runs[0].executor == "користувач"


def test_bare_go_runs_the_planned_complementary_move(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(
        tmp_path,
        fake_agent_cls,
        [HaikuReply(text="generate"), HaikuReply(text="Суддя оцінив ідеї (джерела в LEDGER)")],
    )
    chat.turn("а ще можна використати X")  # the user played Фантазер
    out = chat.turn("/go")
    assert [req.role for req in runner.calls] == ["evaluate"]  # complementary, not duplicate
    assert "Суддя оцінив ідеї" in out  # a short summary of what was done


def test_go_with_style_and_depth_runs_that_sequence(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(
        tmp_path, fake_agent_cls, [HaikuReply(text="переказ прогону")]
    )
    out = chat.turn("/go explore brief")
    assert chat.style == "explore"
    assert [req.role for req in runner.calls] == ["generate", "mutate", "weave"]
    assert "тема сесії" in runner.calls[0].seed_text  # the seed is the session topic
    assert "переказ прогону" in out


def test_bare_go_without_plan_runs_current_style_full(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(tmp_path, fake_agent_cls, [HaikuReply(text="готово")])
    chat.turn("/go")
    roles = [req.role for req in runner.calls]
    assert len(roles) == 6 and roles[0] == "generate" and roles[-1] == "weave"


def test_go_rejects_unknown_token(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(tmp_path, fake_agent_cls, [])
    assert "не зрозумів" in chat.turn("/go щосьдивне")
    assert runner.calls == []


def test_steering_reply_only_converses(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(
        tmp_path,
        fake_agent_cls,
        [HaikuReply(text="steering"), HaikuReply(text="Тема цікава — з чого почнемо?")],
    )
    out = chat.turn("як гадаєш, з чого почати?")
    assert out == "Тема цікава — з чого почнемо?"
    assert runner.calls == [] and session.read_ledger() is None
    # the conversational path still exposes exactly the one tool
    assert model.calls[1]["tools"] == [RUN_BRAINSTORM_TOOL]


# --- the phase DoD as a script ---


def test_debate_reply_plans_adversarially_and_go_runs_it(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(
        tmp_path,
        fake_agent_cls,
        [HaikuReply(text="deepen"), HaikuReply(text="Опонент записав контраргументи")],
        style="debate",
    )
    out = chat.turn("ось стаття, що підтверджує мою позицію")
    assert "Опонента" in out  # planned: the user defends → the agent will attack
    out = chat.turn("/go")
    (req,) = runner.calls
    assert req.role == "oppose"
    assert "виграв" not in out.lower() and "переможець" not in out.lower()


def test_refusal_degrades_to_chat_message(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(
        tmp_path,
        fake_agent_cls,
        [HaikuReply(text="generate")],
        runs=0,  # no budget at all → dispatch refuses before spending
    )
    chat.turn("а ще можна Y")
    out = chat.turn("/go")
    assert "хід відхилено" in out and "бюджет" in out
    assert runner.calls == []
    assert session.read_ledger() is not None  # the user's own move still landed


def test_ledger_command_renders_state(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(
        tmp_path,
        fake_agent_cls,
        [HaikuReply(text="generate"), HaikuReply(text="переказ")],
    )
    chat.turn("а ще можна геотермальні станції")
    chat.turn("/go")
    out = chat.turn("/ledger")
    assert "[open]" in out or "[confirmed]" in out
    assert "сухих поспіль:" in out


def test_repl_quit_leaves_session_on_disk(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(tmp_path, fake_agent_cls, [])
    written: list[str] = []
    run_repl(chat, ["/ledger", "/quit", "/go"], written.append)
    assert session.path.exists()
    assert any("сесію збережено" in ln for ln in written)
    assert runner.calls == []  # nothing after /quit ran


def test_repl_reopen_continues_the_workspace(tmp_path, fake_agent_cls, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    runner = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    haiku = MockHaikuModel([HaikuReply(text="Назва сесії"), HaikuReply(text="готово")])
    # first REPL: create via --new, run one brief brainstorm, quit
    monkeypatch.setattr("sys.stdin", io.StringIO("/go investigate brief\n/quit\n"))
    rc = main(
        ["chat", "--new", "тема про глину", "--style", "investigate"],
        runner=runner,
        config=cfg,
        haiku=haiku,
    )
    assert rc == 0
    (session_dir,) = cfg.sessions_dir.iterdir()
    assert [req.role for req in runner.calls] == ["generate", "evaluate", "weave"]
    assert Session(session_dir).read_ledger() is not None

    # second REPL: explicit continuation — the prior ledger is visible
    runner2 = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    monkeypatch.setattr("sys.stdin", io.StringIO("/ledger\n/quit\n"))
    rc = main(
        ["chat", str(session_dir)],
        runner=runner2,
        config=cfg,
        haiku=MockHaikuModel(),
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "H1" in out and "сухих поспіль" in out  # built on the first REPL's state


def test_chat_requires_session_or_new(tmp_path, capsys):
    rc = main(["chat"], runner=MockAgentRunner({}), config=_cfg(tmp_path), haiku=MockHaikuModel())
    assert rc == 1
    assert "--new" in capsys.readouterr().err
