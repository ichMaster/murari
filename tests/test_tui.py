"""MUR-018 — the TUI scaffold: app shell, panel layout, status bar, session resolution.

Headless: the app runs under Textual's pilot (`run_test`), the pipeline under mock Haiku +
MockAgentRunner — no paid calls, no real terminal.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

import pytest

pytest.importorskip("textual")

from textual.widgets import Input, Static, Tree

from murari.chat import ChatSession
from murari.cli import _resolve_chat_session, main
from murari.config import Config
from murari.haiku import HaikuReply, MockHaikuModel
from murari.runner import MockAgentRunner
from murari.session import create_session, titled_topic
from murari.tui import DocumentPanel, MurariApp, StatusBar, runs_remaining

FIX = Path(__file__).parent / "fixtures" / "contract-v2"
_ALL_ROLES = ("generate", "evaluate", "deepen", "oppose", "mutate", "weave")


def _contracts() -> dict:
    return {r: json.loads((FIX / f"{r}.json").read_text(encoding="utf-8")) for r in _ALL_ROLES}


def _cfg(tmp_path, runs: int = 6) -> Config:
    return Config(runs=runs, max_turns=15, model="m", home=tmp_path)


def _app(tmp_path, fake_agent_cls, replies=(), *, topic="тема сесії", runs=6):
    cfg = _cfg(tmp_path, runs)
    session = create_session(cfg, topic)
    runner = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    model = MockHaikuModel(list(replies))
    chat = ChatSession(cfg, session, runner, model, style="investigate")
    return MurariApp(chat, cfg, runner, model), session, runner, model


_LEDGER_WITH_JOURNAL = (
    "# LEDGER\n\n## Гіпотези\n- [H1][open] ідея\n\n## Прогони\n"
    "- 1: generate(агент) → H1\n- 2: oppose(користувач) → H1 контраргумент\n"
    "- 3: evaluate(агент) → H1 вердикт\n\n## Сухі прогони поспіль: 0\n"
)


# --- composition ---


async def test_app_composes_three_panels_and_status_bar(tmp_path, fake_agent_cls):
    app, session, runner, model = _app(tmp_path, fake_agent_cls)
    async with app.run_test() as pilot:
        assert app.query_one("#chat-log") is not None
        assert app.query_one("#chat-input") is not None
        assert app.query_one("#ledger-panel") is not None
        assert app.query_one("#document-panel") is not None
        bar = app.query_one("#status-bar", StatusBar)
        text = str(bar.content)
        assert "стиль investigate/full" in text and "idle" in text
        await pilot.pause()


async def test_panels_render_workspace_on_open(tmp_path, fake_agent_cls):
    app, session, runner, model = _app(tmp_path, fake_agent_cls)
    session.ledger_file.write_text(_LEDGER_WITH_JOURNAL, encoding="utf-8")
    session.document_file.write_text("# ДОКУМЕНТ\nстан думки\n", encoding="utf-8")
    async with app.run_test() as pilot:
        tree = app.query_one("#ledger-tree", Tree)
        assert any("H1 [open]" in str(n.label) for n in tree.root.children)
        assert "стан думки" in app.query_one("#document-panel", DocumentPanel).last_markdown
        await pilot.pause()


# --- MUR-019: lineage tree, journal, read-only document ---

_LINEAGE_LEDGER = (
    "# LEDGER\n\n## Гіпотези\n"
    "- [H1][confirmed] коренева — джерело: https://e.com/1 — випробувано: 2\n"
    "- [H2][open] друга коренева\n"
    "- [H3][open] мутант — parents: H1 — mutation: invert\n"
    "- [H9][open] гібрид — parents: H1+H2 — mutation: combine\n"
    "\n## Прогони\n- 1: generate(агент) → H1..H2\n"
    "\n## Ранжування\n- H1 — доказ:3 ориг:4 попул:2 поясн:4 — джерела: так\n"
    "\n## Аргументи\n### H1\n- ЗА: довід — джерело: https://e.com/a\n"
    "- ПРОТИ: контра — джерело: https://e.com/b\n"
    "\n## Сухі прогони поспіль: 1\n"
)


async def test_ledger_tree_shows_lineage_scores_and_journal(tmp_path, fake_agent_cls):
    app, session, runner, model = _app(tmp_path, fake_agent_cls)
    async with app.run_test() as pilot:
        session.ledger_file.write_text(_LINEAGE_LEDGER, encoding="utf-8")
        app.refresh_workspace()  # the re-read-on-completion seam
        tree = app.query_one("#ledger-tree", Tree)
        roots = {str(n.label).split()[0]: n for n in tree.root.children}
        assert set(roots) == {"H1", "H2"}  # only true roots at the top level
        h1_children = [str(n.label) for n in roots["H1"].children]
        assert any(lbl.startswith("H3") for lbl in h1_children)
        assert any(lbl.startswith("H9") for lbl in h1_children)
        h2_children = [str(n.label) for n in roots["H2"].children]
        assert any(lbl.startswith("H9") for lbl in h2_children)  # combine → under BOTH parents
        h1_label = str(roots["H1"].label)
        assert "★3424(дж)" in h1_label and "випробувано:2" in h1_label and "1за/1проти" in h1_label
        journal = str(app.query_one("#ledger-journal", Static).content)
        assert "прогін 1: generate(агент)" in journal and "сухих поспіль: 1" in journal
        await pilot.pause()


async def test_document_panel_is_readonly_markdown(tmp_path, fake_agent_cls):
    app, session, runner, model = _app(tmp_path, fake_agent_cls)
    async with app.run_test() as pilot:
        panel = app.query_one("#document-panel", DocumentPanel)
        assert "ще не написано" in panel.last_markdown  # empty state before the first weave
        session.document_file.write_text("# ДОКУМЕНТ\n**стан** аналізу\n", encoding="utf-8")
        app.refresh_workspace()
        assert "**стан** аналізу" in panel.last_markdown
        # read-only pinned: the document surface contains no input-capable widget
        assert not panel.query(Input) and not panel.query("TextArea")
        assert len(app.query(Input)) == 1  # the only Input in the app is the chat input
        await pilot.pause()


async def test_malformed_ledger_renders_error_without_crash(tmp_path, fake_agent_cls):
    app, session, runner, model = _app(tmp_path, fake_agent_cls)
    async with app.run_test() as pilot:
        session.ledger_file.write_text("це не ledger взагалі", encoding="utf-8")
        app.refresh_workspace()
        journal = str(app.query_one("#ledger-journal", Static).content)
        assert "LEDGER не читається" in journal
        assert app.query_one("#chat-input") is not None  # the app is still alive
        await pilot.pause()


# --- MUR-020: async runs, non-blocking chat, status transitions ---


async def test_chat_stays_responsive_during_run(tmp_path, fake_agent_cls):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема сесії")
    started, gate = threading.Event(), threading.Event()
    agent = fake_agent_cls()

    def slow_agent(req):  # the move blocks until the test releases the gate
        started.set()
        assert gate.wait(timeout=5)
        agent(req)

    runner = MockAgentRunner(_contracts(), on_run=slow_agent)
    model = MockHaikuModel([HaikuReply(text="готово")])
    chat = ChatSession(cfg, session, runner, model)
    app = MurariApp(chat, cfg, runner, model)
    async with app.run_test() as pilot:
        inp = app.query_one("#chat-input", Input)
        inp.focus()
        inp.value = "/go brief"
        await pilot.press("enter")
        for _ in range(200):  # wait until the worker actually reached the agent
            if started.is_set():
                break
            await pilot.pause(0.01)
        assert started.is_set()
        bar = str(app.query_one("#status-bar", StatusBar).content)
        assert "копає" in bar  # digging state announced
        # the input is still alive: a second submit is politely refused, nothing queues
        inp.value = "а ще ідея"
        await pilot.press("enter")
        assert any("зачекай" in ln for ln in app.chat_lines)
        assert len(runner.calls) <= 3  # only the /go brief moves — no second dispatch
        gate.set()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "idle" in str(app.query_one("#status-bar", StatusBar).content)
        # completion refreshed the panels and rendered the visually-separated reply
        tree = app.query_one("#ledger-tree", Tree)
        assert len(tree.root.children) >= 1
        assert any(ln.startswith("murari> ") for ln in app.chat_lines)
        assert any("виконую" in ln for ln in app.chat_lines)  # engine progress streamed live


async def test_worker_failure_lands_as_chat_message(tmp_path, fake_agent_cls):
    app, session, runner, model = _app(tmp_path, fake_agent_cls)
    async with app.run_test() as pilot:

        def boom(text):
            raise RuntimeError("бум")

        app.chat.turn = boom  # simulate an unexpected pipeline crash
        inp = app.query_one("#chat-input", Input)
        inp.focus()
        inp.value = "щось"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert any("помилка виконання" in ln for ln in app.chat_lines)
        assert "idle" in str(app.query_one("#status-bar", StatusBar).content)


# --- MUR-021: commands /b, /open + delegation ---


async def _submit(app, pilot, text: str) -> None:
    inp = app.query_one("#chat-input", Input)
    inp.focus()
    inp.value = text
    await pilot.press("enter")
    await app.workers.wait_for_complete()
    await pilot.pause()


async def test_b_creates_named_session_and_switches(tmp_path, fake_agent_cls):
    app, session, runner, model = _app(tmp_path, fake_agent_cls, [HaikuReply(text="Нова назва")])
    async with app.run_test() as pilot:
        old_path = app.chat.session.path
        await _submit(app, pilot, "/b зовсім нова тема")
        assert app.chat.session.path != old_path  # the whole app switched
        assert app.chat.session.read_title() == "Нова назва"
        assert any("нова сесія" in ln for ln in app.chat_lines)
        journal = str(app.query_one("#ledger-journal", Static).content)
        assert "LEDGER ще порожній" in journal  # a fresh /b starts blank


async def test_open_switches_and_bad_path_keeps_running(tmp_path, fake_agent_cls):
    app, session, runner, model = _app(tmp_path, fake_agent_cls)
    other = create_session(_cfg(tmp_path), "інша тема")
    other.ledger_file.write_text(_LEDGER_WITH_JOURNAL, encoding="utf-8")
    async with app.run_test() as pilot:
        await _submit(app, pilot, f"/open {other.path}")
        assert app.chat.session.path == other.path  # explicit continuation
        tree = app.query_one("#ledger-tree", Tree)
        assert any("H1 [open]" in str(n.label) for n in tree.root.children)
        await _submit(app, pilot, "/open /зовсім/не/шлях")
        assert any("не відкрилося" in ln for ln in app.chat_lines)
        assert app.chat.session.path == other.path  # unchanged, app alive


async def test_chat_commands_delegate_to_chatsession(tmp_path, fake_agent_cls):
    app, session, runner, model = _app(tmp_path, fake_agent_cls)
    async with app.run_test() as pilot:
        await _submit(app, pilot, "/style debate")
        assert app.chat.style == "debate"
        assert any("стиль тепер debate" in ln for ln in app.chat_lines)
        await _submit(app, pilot, "/help")
        assert any("/go [стиль]" in ln for ln in app.chat_lines)
        await _submit(app, pilot, "/wat")  # unknown command → the same help text
        assert sum("/quit — вийти" in ln for ln in app.chat_lines) >= 2


async def test_startup_help_mentions_b_and_open(tmp_path, fake_agent_cls):
    app, *_ = _app(tmp_path, fake_agent_cls)
    async with app.run_test() as pilot:
        assert any("/b <тема>" in ln and "/open <шлях>" in ln for ln in app.chat_lines)
        await pilot.pause()


async def test_quit_exits_and_leaves_session_dir(tmp_path, fake_agent_cls):
    app, session, runner, model = _app(tmp_path, fake_agent_cls)
    async with app.run_test() as pilot:
        inp = app.query_one("#chat-input", Input)
        inp.focus()
        inp.value = "/quit"
        await pilot.press("enter")
        await pilot.pause()
    assert session.path.exists()  # the dir remains after exit


# --- MUR-022: the v0.3 DoD as one driven-TUI script ---


async def test_v03_dod_script(tmp_path, fake_agent_cls):
    replies = [
        HaikuReply(text="Назва Б"),  # /b → the Namer titles the fresh session
        HaikuReply(text="brainstorm generate"),  # the router for the chat turn
        HaikuReply(text="steering"),  # detect: nothing to record
        HaikuReply(text="Фантазер додав ідеї"),  # reflect over the refreshed document
        HaikuReply(text="прогін завершено"),  # /go brief presentation
    ]
    app, first_session, runner, model = _app(tmp_path, fake_agent_cls, replies)
    async with app.run_test() as pilot:
        # /b opens a fresh named session
        await _submit(app, pilot, "/b нова тема для DoD")
        dod_session = app.chat.session
        assert dod_session.path != first_session.path
        # a routed chat turn runs one move — the ledger panel fills
        await _submit(app, pilot, "накидай ідей про глину")
        tree = app.query_one("#ledger-tree", Tree)
        assert len(tree.root.children) >= 3
        assert any("Фантазер додав ідеї" in ln for ln in app.chat_lines)
        # a weave-ending run rebuilds the document panel
        panel = app.query_one("#document-panel", DocumentPanel)
        assert "ще не написано" in panel.last_markdown
        await _submit(app, pilot, "/go brief")
        assert "ще не написано" not in panel.last_markdown  # the document exists now
        # /style switches scenarios
        await _submit(app, pilot, "/style debate")
        assert app.chat.style == "debate"
        # /open continues the prior session's document/ledger
        await _submit(app, pilot, f"/open {first_session.path}")
        assert app.chat.session.path == first_session.path
        # /quit exits, everything remains on disk
        inp = app.query_one("#chat-input", Input)
        inp.focus()
        inp.value = "/quit"
        await pilot.press("enter")
        await pilot.pause()
    assert dod_session.path.exists() and first_session.path.exists()
    assert (dod_session.output_dir / "DOCUMENT.md").exists()


# --- status-bar inputs ---


def test_runs_remaining_counts_agent_moves_only(tmp_path):
    cfg = _cfg(tmp_path, runs=6)
    session = create_session(cfg, "тема")
    assert runs_remaining(cfg, session) == 6  # no ledger yet
    session.ledger_file.write_text(_LEDGER_WITH_JOURNAL, encoding="utf-8")
    assert runs_remaining(cfg, session) == 4  # 2 agent moves; the user move is free


# --- CLI wiring ---


def _args(**kw) -> argparse.Namespace:
    return argparse.Namespace(
        session=kw.get("session"), new_topic=kw.get("new_topic"), name=kw.get("name")
    )


def test_session_resolution_shared_with_chat(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    # bare → creates an empty session when none exist
    s1 = _resolve_chat_session(_args(), cfg, MockHaikuModel())
    assert s1 is not None and s1.read_topic() == ""
    # bare again → reopens the most recent
    s2 = _resolve_chat_session(_args(), cfg, MockHaikuModel())
    assert s2.path == s1.path
    # --new → Namer flow with the title heading
    s3 = _resolve_chat_session(
        _args(new_topic="нова тема"), cfg, MockHaikuModel([HaikuReply(text="Назва")])
    )
    assert s3.read_title() == "Назва"
    # explicit bad path → None + printed error
    assert _resolve_chat_session(_args(session=str(tmp_path / "nope")), cfg, None) is None
    assert "cannot open session" in capsys.readouterr().err


def test_tui_without_textual_prints_hint(tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    create_session(cfg, titled_topic("Назва", "тема"))
    monkeypatch.setitem(sys.modules, "murari.tui", None)  # simulate a missing extra
    rc = main(["tui"], runner=MockAgentRunner({}), config=cfg, haiku=MockHaikuModel())
    assert rc == 1
    assert "pip install 'murari[tui]'" in capsys.readouterr().err
