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

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, Markdown, RichLog, Static, Tree

from murari.chat import ChatSession
from murari.config import Config
from murari.ledger import Hypothesis, Ledger, LedgerError
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
