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

import json
import re
from collections.abc import Callable, Iterable

from murari.config import Config
from murari.engine import DEPTHS, STYLES, EngineResult
from murari.haiku import HaikuError, HaikuModel, ToolCall
from murari.ledger import LedgerError
from murari.participant import (
    BRAINSTORM,
    STEERING,
    detect_role,
    find_target,
    record_user_move,
    route_turn,
)
from murari.planner import ROLE_NAMES, choose_style
from murari.presenter import extract_seed, present_result
from murari.runner import AgentRunner
from murari.session import Session
from murari.veduchyi import TOOL_NAME, Dispatcher, Refusal, Veduchyi, result_payload

_HELP = (
    "команди: /style [ключ] — стиль (без ключа: показати; ключі: "
    + "/".join(sorted(STYLES))
    + ") · /go [стиль] [глибина] [Hxx] — запустити брейнсторм над темою сесії "
    "(Hxx — прицілити deepen/oppose/mutate у гіпотезу) · /ledger — стан гіпотез · "
    "/help — ця підказка · /quit — вийти"
)

_HID = re.compile(r"^[HН]\d+$", re.IGNORECASE)  # accepts both Latin H and Cyrillic Н


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
        target = find_target(text, self._ledger_ids())  # an explicit "H2" in the reply
        recorded = ""
        user_role = detect_role(self.model, text)
        if user_role != STEERING:  # the reply itself is a contribution — keep the provenance
            try:
                move = record_user_move(self.session, user_role, text, target_idea=target)
                where = f" →{move.hid}" if move.hid else ""
                recorded = f"записано: твій хід {ROLE_NAMES[user_role]}а ({move.kind}{where})\n"
            except (ValueError, LedgerError) as e:
                recorded = f"(не записав твій хід: {e})\n"
        return recorded + self._launch_move(route.role, text, target=target)

    # --- internals ---

    def _announce(self, text: str) -> None:
        if self.on_progress is not None:
            self.on_progress(text)

    def _ledger_ids(self) -> set[str]:
        try:
            led = self.session.read_ledger()
        except LedgerError:
            return set()
        return led.ids() if led else set()

    def _launch_move(self, role: str, user_text: str, *, target: str | None = None) -> str:
        """One move of `role` — all the router is allowed to launch (deeper runs are /go).
        After the move, Haiku answers the user's reply in substance over the refreshed
        document (`reflect`); the dry run-summary is only the fallback."""
        note = f"хід {ROLE_NAMES[role]}а" + (f" →{target}" if target else "")
        self._announce(f"⚙ викликаю брейнсторм-агента: {note}…")
        seed = extract_seed(self.session.read_topic(), user_text, note)
        args: dict = {"seed": seed, "role": role, "style_step": self.style}
        if target:
            args["target_idea"] = target
        outcome = self.dispatcher.dispatch(
            self.session,
            ToolCall(name=TOOL_NAME, arguments=args, id="chat"),
            on_progress=self.on_progress,
        )
        if isinstance(outcome, Refusal):
            return f"хід відхилено: {outcome.reason}"
        run_json = json.dumps(result_payload(outcome), ensure_ascii=False)
        try:
            answer = self.veduchyi.reflect(user_text, run_json)
        except HaikuError:
            answer = ""
        return f"{note}\n{answer or self._present(outcome)}"

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
        if cmd == "/help":
            return _HELP
        if cmd == "/quit":
            return ""  # the REPL handles exit; the session dir remains
        return _HELP

    def _go(self, arg: str) -> str:
        """`/go [стиль] [глибина] [Hxx]` — the user's explicit way to run something deeper
        than the router's single tiny move. The тема is always the session topic; style and
        depth default to what the chat was started with (`--style`/`--depth`), any token
        given here switches that default, and an H-id pins the single-hypothesis moves
        (deepen/oppose/mutate) to that hypothesis."""
        target: str | None = None
        for token in arg.split():
            if token in STYLES:
                self.style = token
            elif token in DEPTHS:
                self.depth = token
            elif _HID.match(token):
                target = "H" + token[1:]  # normalize a Cyrillic Н to the ledger's Latin H
            else:
                return f"не зрозумів {token!r}: /go [стиль] [глибина: {'/'.join(DEPTHS)}] [Hxx]"
        tgt = f" →{target}" if target else ""
        self._announce(f"⚙ викликаю брейнсторм-агента: стиль {self.style}/{self.depth}{tgt}…")
        seed = extract_seed(self.session.read_topic(), "", f"стиль {self.style}")
        args: dict = {
            "seed": seed,
            "role": STYLES[self.style][0],
            "style_step": self.style,
            "depth": self.depth,
        }
        if target:
            args["target_idea"] = target
        outcome = self.dispatcher.dispatch(
            self.session,
            ToolCall(name=TOOL_NAME, arguments=args, id="chat-go"),
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


def _format_reply(out: str) -> str:
    """The chat's reply, visually separated from the user's input: a `murari>` marker on
    the first line, continuation lines indented under it."""
    lines = out.splitlines() or [""]
    return "\n".join([f"murari> {lines[0]}", *(f"        {ln}" for ln in lines[1:])])


def run_repl(
    chat: ChatSession,
    lines: Iterable[str],
    write: Callable[[str], None] = print,
    *,
    prompt: Callable[[], None] | None = None,
) -> None:
    """Drive a ChatSession over a line source (stdin or a test list). `prompt` (when given)
    is called before each read — the CLI uses it to print a `ти>` input marker. `/quit` —
    or EOF — exits; the session directory always remains on disk."""
    title = chat.session.read_title()
    name = f" — {title}" if title else ""
    write(f"сесія: {chat.session.path.name}{name} (стиль {chat.style}/{chat.depth}); {_HELP}")
    it = iter(lines)
    while True:
        if prompt is not None:
            prompt()
        raw = next(it, None)
        if raw is None:
            break
        line = raw.strip()
        if line == "/quit":
            break
        if not line:
            continue
        out = chat.turn(line)
        if out:
            write("")
            write(_format_reply(out))
    write("")
    write(f"сесію збережено: {chat.session.path}")
