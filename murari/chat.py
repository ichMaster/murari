"""murari — the headless chat REPL (v0.2): the v0.3 TUI's stand-in.

One facilitated turn = reply → detect the user's role → record the user move (free,
provenance-marked) → plan the complementary agent move (adversarial only in debate) →
dispatch through the single-tool boundary → present the result in Ukrainian.

Trigger policy (revised 2026-07-15 per user decision): brainstorm runs launch **only** on
`/go [стиль] [глибина]` — the тема is always the session topic (set at start, or carried by
the reopened session). A classified reply records the user's move and plans the next agent
move, but never launches it; bare `/go` runs that planned move (or, with none pending, the
current style at full depth). The Ведучий converses the rest of the time — grounded in
DOCUMENT.md (summaries, discussion) — and may itself trigger at most a single tiny role
move. Engine failures degrade to a chat message; the workspace is never corrupted.

Commands: /style [key] · /go [стиль] [глибина] · /ledger · /quit (the session dir remains).
Continuation is explicit: `murari chat <session>` reopens; nothing is pulled in silently.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from murari.config import Config
from murari.engine import DEPTHS, STYLES, EngineResult
from murari.haiku import HaikuError, HaikuModel, ToolCall
from murari.ledger import LedgerError, parse_ledger
from murari.participant import STEERING, detect_role, record_user_move
from murari.planner import ROLE_NAMES, PlannedMove, choose_style, plan_next_move
from murari.presenter import extract_seed, present_result
from murari.runner import AgentRunner
from murari.session import Session
from murari.veduchyi import TOOL_NAME, Dispatcher, Refusal, Veduchyi

_HELP = (
    "команди: /style [ключ] — стиль (без ключа: показати; ключі: "
    + "/".join(sorted(STYLES))
    + ") · /go [стиль] [глибина] — запустити брейнсторм над темою сесії · "
    "/ledger — стан гіпотез · /quit — вийти"
)


class ChatSession:
    """One facilitated chat over one session workspace. Deterministic pipeline; the model
    only classifies, converses, and paraphrases — every run goes through the Dispatcher."""

    def __init__(
        self,
        config: Config,
        session: Session,
        runner: AgentRunner,
        model: HaikuModel,
        *,
        style: str | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        self.session = session
        self.model = model
        self.style = choose_style(style, model, session.read_topic())
        self.on_progress = on_progress
        self.dispatcher = Dispatcher(config, runner)
        self.veduchyi = Veduchyi(config, model, runner, session, on_progress=on_progress)
        self._planned: PlannedMove | None = None

    # --- one turn ---

    def turn(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        if text.startswith("/"):
            return self._command(text)
        role = detect_role(self.model, text)
        if role == STEERING:  # just talking — no workspace write, no forced run
            try:
                return self.veduchyi.turn(text)
            except HaikuError as e:
                return f"Ведучий недоступний ({e}); спробуй /go, /ledger або /style"
        try:
            move = record_user_move(self.session, role, text)
        except (ValueError, LedgerError) as e:
            return f"не вдалося записати твій хід: {e}"
        planned = self._plan(role)
        return (
            f"записано: твій хід {ROLE_NAMES[role]}а ({move.kind}); "
            f"заплановано хід {ROLE_NAMES[planned.role]}а — запусти через /go"
        )

    # --- internals ---

    def _plan(self, user_role: str) -> PlannedMove:
        try:
            ledger = self.session.read_ledger()
        except LedgerError:
            ledger = None
        ledger = ledger or parse_ledger(
            "# LEDGER\n\n## Гіпотези\n\n## Прогони\n\n## Сухі прогони поспіль: 0\n"
        )
        self._planned = plan_next_move(self.style, ledger, user_role)
        return self._planned

    def _launch(self, planned: PlannedMove, user_text: str) -> str:
        seed = extract_seed(self.session.read_topic(), user_text, planned.note)
        args: dict = {"seed": seed, "role": planned.role, "style_step": self.style}
        if planned.target:
            args["target_idea"] = planned.target
        outcome = self.dispatcher.dispatch(
            self.session,
            ToolCall(name=TOOL_NAME, arguments=args, id="chat"),
            on_progress=self.on_progress,
        )
        self._planned = None
        if isinstance(outcome, Refusal):
            return f"хід відхилено: {outcome.reason}"
        return f"{planned.note}\n{self._present(outcome)}"

    def _present(self, res: EngineResult) -> str:
        try:
            ledger = self.session.read_ledger()
        except LedgerError:
            ledger = None
        return present_result(self.model, res, ledger)

    def _command(self, text: str) -> str:
        cmd, _, arg = text.partition(" ")
        arg = arg.strip()
        if cmd == "/style":
            if not arg:
                return f"стиль: {self.style}"
            try:
                self.style = choose_style(arg)
            except ValueError as e:
                return f"не вийшло: {e}"
            self._planned = None  # replan from the new template
            return f"стиль тепер {self.style}"
        if cmd == "/go":
            return self._go(arg)
        if cmd == "/ledger":
            return self._render_ledger()
        if cmd == "/quit":
            return ""  # the REPL handles exit; the session dir remains
        return _HELP

    def _go(self, arg: str) -> str:
        """`/go [стиль] [глибина]` — the only way a brainstorm launches; the тема is always
        the session topic (set at start or carried by the reopened session). A style token
        switches the style; bare `/go` runs the pending planned move when one exists,
        otherwise the current style at the given depth (default full)."""
        depth: str | None = None
        for token in arg.split():
            if token in STYLES:
                self.style = token
                self._planned = None  # a new template → the old plan no longer applies
            elif token in DEPTHS:
                depth = token
            else:
                return f"не зрозумів {token!r}: /go [стиль] [глибина: {'/'.join(DEPTHS)}]"
        if depth is None and self._planned is not None:
            return self._launch(self._planned, "")
        seed = extract_seed(self.session.read_topic(), "", f"стиль {self.style}")
        outcome = self.dispatcher.dispatch(
            self.session,
            ToolCall(
                name=TOOL_NAME,
                arguments={
                    "seed": seed,
                    "role": STYLES[self.style][0],
                    "style_step": self.style,
                    "depth": depth or "full",
                },
                id="chat-go",
            ),
            on_progress=self.on_progress,
        )
        self._planned = None
        if isinstance(outcome, Refusal):
            return f"хід відхилено: {outcome.reason}"
        return self._present(outcome)

    def _render_ledger(self) -> str:
        try:
            led = self.session.read_ledger()
        except LedgerError as e:
            return f"LEDGER не читається: {e}"
        if led is None:
            return "LEDGER ще порожній"
        lines = [f"{h.id} [{h.status}] {h.text[:80]}" for h in led.hypotheses]
        lines += [f"прогін {r.n}: {r.move}({r.executor}) → {r.produced}" for r in led.runs]
        lines.append(f"сухих поспіль: {led.dry_streak}")
        return "\n".join(lines)


def run_repl(chat: ChatSession, lines: Iterable[str], write: Callable[[str], None] = print) -> None:
    """Drive a ChatSession over a line source (stdin or a test list). `/quit` — or EOF —
    exits; the session directory always remains on disk."""
    title = chat.session.read_title()
    name = f" — {title}" if title else ""
    write(f"сесія: {chat.session.path.name}{name} (стиль {chat.style}); {_HELP}")
    for raw in lines:
        line = raw.strip()
        if line == "/quit":
            break
        if not line:
            continue
        out = chat.turn(line)
        if out:
            write(out)
    write(f"сесію збережено: {chat.session.path}")
