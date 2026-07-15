"""MUR-017 (revised 2026-07-15) — the chat REPL with the Haiku router.

The flow per reply: one Haiku call classifies (document talk vs a brainstorm ask); document
talk goes to a second Haiku call grounded in DOCUMENT.md; a brainstorm ask records the
user's contribution and launches ONE move of the routed role — deeper runs only via
`/go [стиль] [глибина]`. Mock Haiku + MockAgentRunner/FakeAgent — no paid calls anywhere.
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


# --- the router: document talk vs a single routed move ---


def test_document_question_stays_a_haiku_conversation(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(
        tmp_path,
        fake_agent_cls,
        [HaikuReply(text="document"), HaikuReply(text="У документі три відкриті гіпотези.")],
    )
    out = chat.turn("про що зараз документ?")
    assert out == "У документі три відкриті гіпотези."
    assert runner.calls == [] and session.read_ledger() is None
    # the conversational call still exposes exactly the one tool
    assert model.calls[1]["tools"] == [RUN_BRAINSTORM_TOOL]


def test_brainstorm_ask_records_and_runs_one_routed_move(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(
        tmp_path,
        fake_agent_cls,
        [
            HaikuReply(text="brainstorm evaluate"),  # the router picks the agent move
            HaikuReply(text="generate"),  # detect: the user contributed an idea
            HaikuReply(text="Суддя оцінив ідеї (джерела в LEDGER)"),  # presentation
        ],
    )
    out = chat.turn("а ще можна використати X")
    assert [req.role for req in runner.calls] == ["evaluate"]  # exactly one move
    assert "записано: твій хід Фантазера" in out
    assert "Суддя оцінив ідеї" in out
    led = session.read_ledger()
    assert led.runs[0].executor == "користувач"  # the contribution kept its provenance


def test_router_launches_at_most_one_move(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(
        tmp_path,
        fake_agent_cls,
        [
            HaikuReply(text="brainstorm generate"),
            HaikuReply(text="steering"),  # nothing to record — just run the move
            HaikuReply(text="Фантазер накидав ідей"),
        ],
    )
    out = chat.turn("накидай ідей")
    assert [req.role for req in runner.calls] == ["generate"]
    assert "Фантазер накидав ідей" in out


def test_router_doubt_routes_to_document(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(
        tmp_path,
        fake_agent_cls,
        [HaikuReply(text="галюн якийсь"), HaikuReply(text="поговорімо")],
    )
    assert chat.turn("щось незрозуміле") == "поговорімо"
    assert runner.calls == []


# --- /go: the user's explicit deep run ---


def test_go_with_style_and_depth_runs_that_sequence(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(
        tmp_path, fake_agent_cls, [HaikuReply(text="переказ прогону")]
    )
    out = chat.turn("/go explore brief")
    assert chat.style == "explore"
    assert [req.role for req in runner.calls] == ["generate", "mutate", "weave"]
    assert "тема сесії" in runner.calls[0].seed_text  # the seed is the session topic
    assert "переказ прогону" in out


def test_bare_go_runs_current_style_full(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(tmp_path, fake_agent_cls, [HaikuReply(text="готово")])
    chat.turn("/go")
    roles = [req.role for req in runner.calls]
    assert len(roles) == 6 and roles[0] == "generate" and roles[-1] == "weave"


def test_start_depth_is_the_go_default(tmp_path, fake_agent_cls, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    runner = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    haiku = MockHaikuModel([HaikuReply(text="Назва"), HaikuReply(text="готово")])
    monkeypatch.setattr("sys.stdin", io.StringIO("/go\n/quit\n"))
    rc = main(
        ["chat", "--new", "тема", "--style", "investigate", "--depth", "brief"],
        runner=runner,
        config=cfg,
        haiku=haiku,
    )
    assert rc == 0
    # bare /go honored the start depth: investigate/brief = 3 moves
    assert [req.role for req in runner.calls] == ["generate", "evaluate", "weave"]
    assert "investigate/brief" in capsys.readouterr().out  # shown in the REPL header


def test_go_rejects_unknown_token(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(tmp_path, fake_agent_cls, [])
    assert "не зрозумів" in chat.turn("/go щосьдивне")
    assert runner.calls == []


def test_go_refusal_degrades_to_chat_message(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(
        tmp_path,
        fake_agent_cls,
        [],
        runs=2,  # brief needs 3 moves → refused before spending
    )
    out = chat.turn("/go brief")
    assert "хід відхилено" in out and "бюджет" in out
    assert runner.calls == []


# --- state & lifecycle ---


def test_ledger_command_renders_state(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(
        tmp_path,
        fake_agent_cls,
        [HaikuReply(text="переказ")],
    )
    chat.turn("/go investigate brief")
    out = chat.turn("/ledger")
    assert "[open]" in out or "[confirmed]" in out
    assert "сухих поспіль:" in out


def test_repl_visually_separates_prompt_and_reply(tmp_path, fake_agent_cls):
    chat, session, runner, model = _chat(
        tmp_path,
        fake_agent_cls,
        [HaikuReply(text="document"), HaikuReply(text="перший рядок\nдругий рядок")],
    )
    written: list[str] = []
    prompts: list[str] = []
    run_repl(chat, ["про що документ?"], written.append, prompt=lambda: prompts.append("ти> "))
    assert prompts == ["ти> ", "ти> "]  # before the reply and before the EOF read
    reply = next(ln for ln in written if ln.startswith("murari> "))
    assert reply == "murari> перший рядок\n        другий рядок"  # continuation indented
    assert "" in written  # a blank line separates input from the reply


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


def test_bare_chat_creates_empty_session_when_none_exist(tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("/quit\n"))
    rc = main(["chat"], runner=MockAgentRunner({}), config=cfg, haiku=MockHaikuModel())
    assert rc == 0
    (session_dir,) = cfg.sessions_dir.iterdir()  # an empty session was created
    assert "порожня" in capsys.readouterr().out
    assert Session(session_dir).read_topic() == ""


def test_bare_chat_reopens_the_most_recent_session(tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    create_session(cfg, "стара тема", stamp="20260101-000001")
    recent = create_session(cfg, "нова тема", stamp="20260102-000001")
    monkeypatch.setattr("sys.stdin", io.StringIO("/quit\n"))
    rc = main(["chat"], runner=MockAgentRunner({}), config=cfg, haiku=MockHaikuModel())
    assert rc == 0
    out = capsys.readouterr().out
    assert f"відкрито останню сесію: {recent.path.name}" in out
