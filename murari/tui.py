"""murari — the Textual TUI (v0.3): three panels over one session workspace.

Layout (decided v0.3, revised 2026-07-16 per user): the **working document on the left** —
the deliverable gets the big surface; **right column split** — ledger on top, chat (log +
input) below; a status bar at the bottom with style/depth, the current move, runs remaining,
and idle/«копає». The TUI only
*reads* the workspace and drives the existing v0.2 `ChatSession` — no new seams: every run
still passes the single-tool boundary, and the document stays read-only to the user.

This module imports `textual` at the top — the CLI imports it lazily so `murari tui`
without the `[tui]` extra degrades to an install hint while everything else keeps working.
"""

from __future__ import annotations

import time
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, Markdown, RichLog, Static, Tree
from textual.worker import Worker, WorkerState

from murari.chat import _HELP, ChatSession, _format_reply
from murari.config import Config
from murari.haiku import HaikuModel, Namer
from murari.ledger import Hypothesis, Ledger, LedgerError
from murari.runner import AgentRunner
from murari.session import Session, SessionError, create_session, open_session, titled_topic


def runs_remaining(config: Config, session: Session) -> int:
    """Display-only budget hint for the status bar: `MURARI_RUNS` minus the agent moves
    already journaled this session (user moves are free and don't count)."""
    try:
        led = session.read_ledger()
    except LedgerError:
        return config.runs
    if led is None:
        return config.runs
    agent_moves = sum(1 for r in led.runs if r.executor == "агент")
    return max(0, config.runs - agent_moves)


class StatusBar(Static):
    """One line of truth: style/depth · current move · runs remaining · idle/копає."""

    def set_state(
        self, *, style: str, depth: str, move: str | None, runs_left: int, digging: bool
    ) -> None:
        state = "копає" if digging else "idle"
        self.update(
            f"стиль {style}/{depth} · хід: {move or '—'} · залишилось ходів: {runs_left} · {state}"
        )


def _node_label(led: Ledger, h: Hypothesis) -> str:
    """One tree line per hypothesis: id, status, ★ scores, «випробувано», за/проти, text."""
    parts = [f"{h.id} [{h.status}]"]
    s = led.score(h.id)
    if s is not None:
        mark = "дж" if s.sourced else "чорн"
        parts.append(f"★{s.evidence}{s.originality}{s.popularity}{s.explanatory}({mark})")
    if h.tested:
        parts.append(f"випробувано:{h.tested}")
    args = led.arguments_for(h.id)
    if args:
        za = sum(1 for a in args if a.side == "за")
        parts.append(f"{za}за/{len(args) - za}проти")
    parts.append(h.text[:48])
    return " ".join(parts)


class LedgerPanel(VerticalScroll):
    """The ledger surface: the lineage tree (a `combine` child appears under each parent)
    with the run journal underneath. Read side only — the panel never writes files."""

    def compose(self) -> ComposeResult:
        yield Tree("LEDGER", id="ledger-tree")
        yield Static(id="ledger-journal")

    def render_session(self, session: Session) -> None:
        tree = self.query_one("#ledger-tree", Tree)
        journal = self.query_one("#ledger-journal", Static)
        tree.clear()
        try:
            led = session.read_ledger()
        except LedgerError as e:  # malformed state renders as an error, the app lives on
            journal.update(f"LEDGER не читається: {e}")
            return
        if led is None:
            journal.update("LEDGER ще порожній")
            return
        tree.root.expand()
        nodes: dict[str, list] = {}  # hid → the tree nodes that carry it (combine: several)
        for h in led.hypotheses:
            label = Text(_node_label(led, h))  # plain text — `[open]` is not Rich markup
            parents = [p for p in h.parents if p in nodes]
            if parents:
                added = [nodes[p][0].add(label, expand=True) for p in parents]
            else:
                added = [tree.root.add(label, expand=True)]
            nodes[h.id] = added
        lines = [f"прогін {r.n}: {r.move}({r.executor}) → {r.produced}" for r in led.runs]
        lines.append(f"сухих поспіль: {led.dry_streak}")
        journal.update("\n".join(lines))


class DocumentPanel(VerticalScroll):
    """The working document rendered as markdown — **read-only to the user** (accepted
    2026-07-05: document wishes are orders to Ткач through chat, never file edits). The
    panel deliberately contains no input-capable widget."""

    last_markdown: str = ""  # what was last rendered (tests read this, not textual internals)

    def compose(self) -> ComposeResult:
        yield Markdown("", id="document-md")

    def render_session(self, session: Session) -> None:
        doc = session.read_document()
        self.last_markdown = doc or "*DOCUMENT.md ще не написано — перший weave створить його.*"
        self.query_one("#document-md", Markdown).update(self.last_markdown)


class MurariApp(App):
    """The three-panel murari interface over one `ChatSession`."""

    CSS = """
    #document-pane { width: 3fr; }
    #side-pane { width: 2fr; }
    #chat-pane { height: 1fr; }
    #chat-log { height: 1fr; border: round $surface-lighten-2; }
    #chat-input { dock: bottom; }
    #ledger-panel { height: 1fr; border: round $surface-lighten-2; overflow-y: auto; }
    #document-panel { height: 1fr; border: round $surface-lighten-2; overflow-y: auto; }
    #status-bar { dock: bottom; height: 1; background: $surface-lighten-1; }
    """

    def __init__(
        self, chat: ChatSession, config: Config, runner: AgentRunner, model: HaikuModel
    ) -> None:
        super().__init__()
        self.chat = chat
        self.config = config
        self.runner = runner  # /b and /open build fresh ChatSessions over the same seams
        self.model = model
        self.chat_lines: list[str] = []  # everything written to the chat log (tests read this)
        self._busy = False  # one run at a time — a second submit is politely refused
        self._dig_started = 0.0
        self._dig_label = "копає"

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="document-pane"):
                yield DocumentPanel(id="document-panel")
            with Vertical(id="side-pane"):
                yield LedgerPanel(id="ledger-panel")
                with Vertical(id="chat-pane"):
                    yield RichLog(id="chat-log", wrap=True, markup=False)
                    yield Input(placeholder="ти> …", id="chat-input")
        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        session = self.chat.session
        title = session.read_title()
        name = f" — {title}" if title else ""
        self._write_chat(f"сесія: {session.path.name}{name}")
        self._write_chat(_HELP + " · /b <тема> — нова сесія · /open <шлях> — продовжити іншу")
        # progress from the worker thread streams into the chat log (announce + engine lines)
        self.chat.on_progress = self._progress_from_thread
        self.chat.veduchyi.on_progress = self._progress_from_thread
        self.refresh_workspace()
        self.set_status(move=None, digging=False)

    # --- async runs (MUR-020): the chat stays live while the agent digs ---

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        if text == "/quit":
            self.exit()  # the session directory remains on disk
            return
        if self._busy:  # decided policy: refuse politely, never queue silently
            self._write_chat("⏳ агент ще копає — зачекай завершення ходу")
            return
        self._write_chat(f"ти> {text}")
        cmd, _, arg = text.partition(" ")
        if cmd == "/b":  # a fresh blank session — no implicit cross-session memory
            self._cmd_b(arg.strip())
            return
        if cmd == "/open":  # explicit continuation of another session
            self._cmd_open(arg.strip())
            return
        self._busy = True
        self._dig_started = time.monotonic()
        self._dig_label = "копає"
        self.set_status(move=None, digging=True)
        self._run_turn(text)

    # --- session switching (MUR-021): /b and /open re-point every panel ---

    def _cmd_b(self, topic: str) -> None:
        if not topic:
            self._write_chat("вкажи тему: /b <тема>")
            return
        title = Namer(self.model).name(topic)
        session = create_session(self.config, titled_topic(title, topic))
        self._switch_session(session, f"нова сесія: {session.path.name} — {title}")

    def _cmd_open(self, arg: str) -> None:
        if not arg:
            self._write_chat("вкажи шлях: /open <session-dir>")
            return
        try:
            session = open_session(Path(arg))
        except SessionError as e:
            self._write_chat(f"не відкрилося: {e}")
            return
        self._switch_session(session, f"відкрито: {session.path.name}")

    def _switch_session(self, session: Session, note: str) -> None:
        """A fresh ChatSession over the new workspace (style/depth defaults carry over);
        panels and the status bar re-point immediately."""
        self.chat = ChatSession(
            self.config,
            session,
            self.runner,
            self.model,
            style=self.chat.style,
            depth=self.chat.depth,
        )
        self.chat.on_progress = self._progress_from_thread
        self.chat.veduchyi.on_progress = self._progress_from_thread
        self._write_chat(note)
        self.refresh_workspace()
        self.set_status(move=None, digging=False)

    @work(thread=True, name="turn", exit_on_error=False)
    def _run_turn(self, text: str) -> str:
        return self.chat.turn(text)  # minutes-long — lives in a worker thread

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.name != "turn":
            return
        if event.state == WorkerState.SUCCESS:
            self._finish_turn(str(event.worker.result or ""))
        elif event.state in (WorkerState.ERROR, WorkerState.CANCELLED):
            self._write_chat(f"помилка виконання: {event.worker.error}")
            self._finish_turn("")

    def _finish_turn(self, reply: str) -> None:
        self._busy = False
        self.refresh_workspace()  # panels update the moment the move completes
        self.set_status(move=None, digging=False)
        if reply:
            self._write_chat("")
            self._write_chat(_format_reply(reply))

    def _progress_from_thread(self, line: str) -> None:
        """on_progress arrives on the worker thread — marshal it onto the UI thread."""
        self.call_from_thread(self._handle_progress, line)

    def _handle_progress(self, line: str) -> None:
        self._write_chat(line)
        if line.startswith("⚙"):  # the announce line names what is being dug
            self._dig_label = line.removeprefix("⚙ викликаю брейнсторм-агента:").strip(" …")
        elapsed = time.monotonic() - self._dig_started
        self.set_status(move=f"{self._dig_label} · {elapsed:.0f}s", digging=True)

    def _write_chat(self, line: str) -> None:
        self.chat_lines.append(line)
        self.query_one("#chat-log", RichLog).write(line)

    # --- shared surfaces ---

    def refresh_workspace(self) -> None:
        """Both workspace panels re-read their files (session open, move completion)."""
        self.query_one("#ledger-panel", LedgerPanel).render_session(self.chat.session)
        self.query_one("#document-panel", DocumentPanel).render_session(self.chat.session)

    def set_status(self, *, move: str | None, digging: bool) -> None:
        self.query_one("#status-bar", StatusBar).set_state(
            style=self.chat.style,
            depth=self.chat.depth,
            move=move,
            runs_left=runs_remaining(self.config, self.chat.session),
            digging=digging,
        )
