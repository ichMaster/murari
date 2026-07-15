"""murari — the move planner (v0.2): the deterministic half of facilitation.

Given the style, the ledger state, and the role the user is live-playing, pick the next
agent move. Complementarity is the default — the agents play the roles the user doesn't;
`debate` is the deliberate exception (adversarial pairing, sides can swap, and **no winner
is ever declared** — the product is both sides' arguments in the LEDGER). User orders
(Суддя/Ткач-замовлення) map straight to the ordered move. Style selection: an explicit
`/style` always wins; otherwise Haiku infers one from the topic framing with `investigate`
as the safe default. Deviation stays the engine's rule (two dry moves → the agent's
`next_role` or a fallback, justification logged); the planner only surfaces it verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass

from murari.engine import DEFAULT_STYLE, STYLES, EngineResult, select_target
from murari.haiku import HaikuModel
from murari.ledger import Ledger
from murari.participant import STEERING

ROLE_NAMES = {
    "generate": "Фантазер",
    "evaluate": "Суддя",
    "deepen": "Дослідник",
    "oppose": "Опонент",
    "mutate": "Алхімік",
    "weave": "Ткач",
}

# The user-role keys the writer records as ORDERS — they request that agent move directly.
_ORDERS = ("evaluate", "weave")
_TARGET_MOVES = ("deepen", "oppose", "mutate")

_STYLE_SYSTEM = (
    "Обери стиль брейнштормінгу під формулювання теми. Відповідай РІВНО одним ключем: "
    "explore — «накидай варіантів», багато ідей вшир; debate — суперечка за/проти одного "
    "твердження; riff — розкрутити одну конкретну ідею; investigate — питання, що потребує "
    "перевірки фактами (дефолт); evolve — вивести найкраще з наявного; premortem — «чому це "
    "провалиться». Сумніваєшся — investigate."
)


@dataclass(frozen=True)
class PlannedMove:
    """One defensible next agent move: the role, its target (if any), and a chat-facing
    note. The note never crowns a winner — debate frames both sides as the product."""

    role: str
    target: str | None
    note: str


def _preference(style: str) -> tuple[str, ...]:
    """The style's move preference — its sequence order, deduped (weave stays last)."""
    return tuple(dict.fromkeys(STYLES[style]))


def _applicable(move: str, ledger: Ledger) -> bool:
    """State rule: generate refills breadth only when nothing is open to work on; every
    other move needs at least one hypothesis in the ledger."""
    has_any = bool(ledger.hypotheses)
    if move == "generate":
        return not any(h.status == "open" for h in ledger.hypotheses)
    return has_any


def _with_target(role: str, ledger: Ledger, note: str) -> PlannedMove:
    target = select_target(role, ledger) if role in _TARGET_MOVES else None
    return PlannedMove(role=role, target=target, note=note)


def plan_next_move(style: str, ledger: Ledger, user_role: str) -> PlannedMove:
    """The next agent move for (style, ledger, user's live role).

    Orders map directly; `debate` pairs adversarially against the user's side; every other
    style is complementary — never the user's own role. Targets reuse the engine's
    strongest-survivor selection."""
    if style not in STYLES:
        raise ValueError(f"unknown style: {style!r}")

    if user_role in _ORDERS:  # a user order IS the request for that agent move
        return _with_target(user_role, ledger, f"виконую замовлення: хід {ROLE_NAMES[user_role]}а")

    if style == "debate" and user_role != STEERING:
        if user_role == "oppose":  # the user attacks → the agent defends with evidence
            return _with_target(
                "deepen",
                ledger,
                "адверсарна пара: ти атакуєш — я збираю докази захисту; переможця немає, "
                "продуктом є аргументи обох сторін у LEDGER",
            )
        return _with_target(  # the user defends/brings material → the agent attacks
            "oppose",
            ledger,
            "адверсарна пара: ти захищаєш — я атакую; переможця немає, продуктом є "
            "аргументи обох сторін у LEDGER",
        )

    order = _preference(style)
    if user_role == "oppose":  # an actively opposing user → favor deepen/evaluate
        favored = [m for m in ("deepen", "evaluate") if m in order]
        order = tuple(favored + [m for m in order if m not in favored])
    candidates = [m for m in order if m != user_role or style == "debate"]

    for move in candidates:
        if _applicable(move, ledger):
            who = ROLE_NAMES[move]
            note = (
                f"доповнюю твою роль: хід {who}а"
                if user_role != STEERING
                else f"за станом LEDGER далі хід {who}а"
            )
            return _with_target(move, ledger, note)
    # nothing applicable (e.g. an empty ledger with everything filtered) — fresh material
    return PlannedMove(role="generate", target=None, note="порожній LEDGER: починаю з ідей")


def choose_style(
    explicit: str | None = None, model: HaikuModel | None = None, topic: str = ""
) -> str:
    """The session style: an explicit key always wins (mid-session change included);
    otherwise infer from the topic framing via Haiku, defaulting to `investigate` on any
    doubt or failure. Never raises for inference — only an invalid explicit key errors."""
    if explicit:
        if explicit not in STYLES:
            raise ValueError(f"unknown style: {explicit!r}; available: {sorted(STYLES)}")
        return explicit
    if model is None or not topic.strip():
        return DEFAULT_STYLE
    try:
        reply = model.complete(_STYLE_SYSTEM, [{"role": "user", "content": topic[:2000]}])
    except Exception:
        return DEFAULT_STYLE
    text = (reply.text or "").strip()
    label = text.split()[0].strip(".,:;!«»\"'").lower() if text else ""
    return label if label in STYLES else DEFAULT_STYLE


def deviation_notes(res: EngineResult) -> list[str]:
    """The engine's deviation justifications, verbatim — the chat surfaces these instead of
    second-guessing the deterministic rule (open question closed for v0.2)."""
    return [m.deviated for m in res.moves if m.deviated]
