"""murari — the headless chat REPL (v0.2): the v0.3 TUI's stand-in.

One facilitated turn = reply → detect the user's role → record the user move (free,
provenance-marked) → plan the complementary agent move (adversarial only in debate) →
dispatch through the single-tool boundary → present the result in Ukrainian.

Trigger policy (open question closed for v0.2): a reply classified into a role
**auto-launches** the planned move — that's the facilitation contract of the DoD; a
steering reply only converses (Ведучий may still decide to call the tool itself), and
`/go` always forces the planned move. Engine failures degrade to a chat message — the
workspace is never corrupted (the engine rolls back only the failed move).

Commands: /style [key] · /go · /ledger · /quit (the session dir remains on disk).
Continuation is explicit: `murari chat <session>` reopens; nothing is pulled in silently.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from murari.config import Config
from murari.engine import STYLES, EngineResult
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
    + ") · /go — запустити запланований хід · /ledger — стан гіпотез · /quit — вийти"
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
        auto_trigger: bool = True,  # the decided v0.2 policy; tests may switch it off
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        self.session = session
        self.model = model
        self.style = choose_style(style, model, session.read_topic())
        self.auto_trigger = auto_trigger
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
        recorded = f"записано: твій хід {ROLE_NAMES[role]}а ({move.kind})"
        if not self.auto_trigger:
            return f"{recorded}; заплановано {ROLE_NAMES[planned.role]} — запусти через /go"
        return f"{recorded}\n{self._launch(planned, text)}"

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
            planned = self._planned or self._plan(STEERING)
            return self._launch(planned, "")
        if cmd == "/ledger":
            return self._render_ledger()
        if cmd == "/quit":
            return ""  # the REPL handles exit; the session dir remains
        return _HELP

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
