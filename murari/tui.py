"""murari — the Textual TUI (v0.3): three panels over one session workspace.

Layout (decided v0.3, closes the roadmap open question): **chat on the left** (log + input);
**right column split** — ledger on top, the working document below; a status bar at the
bottom with style/depth, the current move, runs remaining, and idle/«копає». The TUI only
*reads* the workspace and drives the existing v0.2 `ChatSession` — no new seams: every run
still passes the single-tool boundary, and the document stays read-only to the user.

This module imports `textual` at the top — the CLI imports it lazily so `murari tui`
without the `[tui]` extra degrades to an install hint while everything else keeps working.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, RichLog, Static

from murari.chat import ChatSession
from murari.config import Config
from murari.ledger import LedgerError
from murari.session import Session


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


class LedgerPanel(Static):
    """The ledger surface (v0.3 scaffold: a text summary; the lineage tree lands in
    MUR-019). Read side only — the panel never writes workspace files."""

    def render_session(self, session: Session) -> None:
        try:
            led = session.read_ledger()
        except LedgerError as e:
            self.update(f"LEDGER не читається: {e}")
            return
        if led is None:
            self.update("LEDGER ще порожній")
            return
        lines = [f"{h.id} [{h.status}] {h.text[:60]}" for h in led.hypotheses]
        lines.append(f"сухих поспіль: {led.dry_streak}")
        self.update("\n".join(lines))


class DocumentPanel(Static):
    """The working document, read-only to the user (accepted 2026-07-05: document wishes
    are orders to Ткач through chat, never file edits)."""

    def render_session(self, session: Session) -> None:
        doc = session.read_document()
        self.update(doc if doc else "DOCUMENT.md ще не написано (перший weave створить його)")


class MurariApp(App):
    """The three-panel murari interface over one `ChatSession`."""

    CSS = """
    #chat-pane { width: 3fr; }
    #side-pane { width: 2fr; }
    #chat-log { height: 1fr; border: round $surface-lighten-2; }
    #chat-input { dock: bottom; }
    #ledger-panel { height: 1fr; border: round $surface-lighten-2; overflow-y: auto; }
    #document-panel { height: 1fr; border: round $surface-lighten-2; overflow-y: auto; }
    #status-bar { dock: bottom; height: 1; background: $surface-lighten-1; }
    """

    def __init__(self, chat: ChatSession, config: Config) -> None:
        super().__init__()
        self.chat = chat
        self.config = config

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="chat-pane"):
                yield RichLog(id="chat-log", wrap=True, markup=False)
                yield Input(placeholder="ти> …", id="chat-input")
            with Vertical(id="side-pane"):
                yield LedgerPanel(id="ledger-panel")
                yield DocumentPanel(id="document-panel")
        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        session = self.chat.session
        title = session.read_title()
        name = f" — {title}" if title else ""
        log = self.query_one("#chat-log", RichLog)
        log.write(f"сесія: {session.path.name}{name}")
        self.refresh_workspace()
        self.set_status(move=None, digging=False)

    # --- shared surfaces (MUR-019 wires live refresh into real runs) ---

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
