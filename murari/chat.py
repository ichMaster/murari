"""murari — the headless chat REPL (v0.2): the v0.3 TUI's stand-in.

One facilitated turn = reply → detect the user's role → record the user move (free,
provenance-marked) → plan the complementary agent move (adversarial only in debate) →
dispatch through the single-tool boundary → present the result in Ukrainian.

Turn routing (revised 2026-07-15 per user decision): every reply goes through a Haiku
router. A question about the existing document (or plain talk) stays a Haiku conversation
grounded in DOCUMENT.md; a brainstorm ask records the user's contribution (when there is
one) and immediately launches **one move** of the role the router chose — the router may
launch nothing deeper. Deeper runs are the user's explicit `/go [стиль] [глибина]` over
the session topic (set at start or carried by the reopened session). Engine failures
degrade to a chat message; the workspace is never corrupted.

Commands: /style [key] · /go [стиль] [глибина] · /ledger · /quit (the session dir remains).
Continuation is explicit: `murari chat <session>` reopens; nothing is pulled in silently.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from murari.config import Config
from murari.engine import DEPTHS, STYLES, EngineResult
from murari.haiku import HaikuError, HaikuModel, ToolCall
from murari.ledger import LedgerError
from murari.participant import (
    BRAINSTORM,
    STEERING,
    detect_role,
    record_user_move,
    route_turn,
)
from murari.planner import ROLE_NAMES, choose_style
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
        depth: str | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        self.session = session
        self.model = model
        self.style = choose_style(style, model, session.read_topic())
        self.depth = depth or "full"  # the default depth /go runs at (set at start)
        self.on_progress = on_progress
        self.dispatcher = Dispatcher(config, runner)
        self.veduchyi = Veduchyi(config, model, runner, session, on_progress=on_progress)

    # --- one turn ---

    def turn(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        if text.startswith("/"):
            return self._command(text)
        route = route_turn(self.model, text)
        if route.mode != BRAINSTORM:  # document talk / summaries / plain conversation
            try:
                return self.veduchyi.turn(text)
            except HaikuError as e:
                return f"Ведучий недоступний ({e}); спробуй /go, /ledger або /style"
        recorded = ""
        user_role = detect_role(self.model, text)
        if user_role != STEERING:  # the reply itself is a contribution — keep the provenance
            try:
                move = record_user_move(self.session, user_role, text)
                recorded = f"записано: твій хід {ROLE_NAMES[user_role]}а ({move.kind})\n"
            except (ValueError, LedgerError) as e:
                recorded = f"(не записав твій хід: {e})\n"
        return recorded + self._launch_move(route.role, text)

    # --- internals ---

    def _launch_move(self, role: str, user_text: str) -> str:
        """One move of `role` — all the router is allowed to launch (deeper runs are /go)."""
        note = f"хід {ROLE_NAMES[role]}а"
        seed = extract_seed(self.session.read_topic(), user_text, note)
        outcome = self.dispatcher.dispatch(
            self.session,
            ToolCall(
                name=TOOL_NAME,
                arguments={"seed": seed, "role": role, "style_step": self.style},
                id="chat",
            ),
            on_progress=self.on_progress,
        )
        if isinstance(outcome, Refusal):
            return f"хід відхилено: {outcome.reason}"
        return f"{note}\n{self._present(outcome)}"

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
            return f"стиль тепер {self.style}"
        if cmd == "/go":
            return self._go(arg)
        if cmd == "/ledger":
            return self._render_ledger()
        if cmd == "/quit":
            return ""  # the REPL handles exit; the session dir remains
        return _HELP

    def _go(self, arg: str) -> str:
        """`/go [стиль] [глибина]` — the user's explicit way to run something deeper than
        the router's single tiny move. The тема is always the session topic; style and depth
        default to what the chat was started with (`--style`/`--depth`), and any token given
        here switches that default for the rest of the session."""
        for token in arg.split():
            if token in STYLES:
                self.style = token
            elif token in DEPTHS:
                self.depth = token
            else:
                return f"не зрозумів {token!r}: /go [стиль] [глибина: {'/'.join(DEPTHS)}]"
        seed = extract_seed(self.session.read_topic(), "", f"стиль {self.style}")
        outcome = self.dispatcher.dispatch(
            self.session,
            ToolCall(
                name=TOOL_NAME,
                arguments={
                    "seed": seed,
                    "role": STYLES[self.style][0],
                    "style_step": self.style,
                    "depth": self.depth,
                },
                id="chat-go",
            ),
            on_progress=self.on_progress,
        )
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
    write(f"сесія: {chat.session.path.name}{name} (стиль {chat.style}/{chat.depth}); {_HELP}")
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
