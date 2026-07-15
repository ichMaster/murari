"""murari — the user as the seventh player (v0.2).

Role detection classifies a chat reply into the brainstorm role the human is playing
(strategies.md §«Користувач як учасник»); a deterministic writer then records the
contribution in the shared workspace exactly like a role move: provenance-marked
(`born_from: user`), journaled with the executor (`(користувач)`), H-ids allocated
sequentially. Invariants hold by construction — user moves never touch DOCUMENT.md
(Ткач-замовлення is an order for the next weave, not a file write), never spend
`MURARI_RUNS` (user moves are free), and never mint a verdict (the source gate: user
claims land as `open` candidates). Haiku only classifies; plain Python writes — the
model touches no files.
"""

from __future__ import annotations

from dataclasses import dataclass

from murari.haiku import HaikuModel
from murari.ledger import parse_ledger
from murari.session import Session

# The user-role keys mirror the agent move they cover. `evaluate`/`weave` are ORDERS (the
# user asks for that move), the rest are contributions; `steering` is "just talking".
USER_ROLES = ("generate", "deepen", "oppose", "mutate", "evaluate", "weave")
STEERING = "steering"
_ORDERS = ("evaluate", "weave")

_DETECT_SYSTEM = (
    "Класифікуй репліку учасника брейнштормінгу в роль. Відповідай РІВНО одним словом:\n"
    "generate — приніс нову ідею чи варіанти («а ще можна X, Y, Z…»)\n"
    "deepen — приніс матеріал: факт, статтю, цифру\n"
    "oppose — контраргумент («це не спрацює, бо…»)\n"
    "mutate — «а що якщо навпаки / ×100 / в іншій галузі?»\n"
    "evaluate — замовлення вердикту («перевір оце твердження»)\n"
    "weave — замовлення Ткачу щодо документа («перепиши висновок так…»)\n"
    "steering — керування розмовою або незрозуміло. Сумніваєшся — steering."
)

_EMPTY_LEDGER = "# LEDGER\n\n## Гіпотези\n\n## Прогони\n\n## Сухі прогони поспіль: 0\n"


def detect_role(model: HaikuModel, reply_text: str) -> str:
    """The role the user is playing in `reply_text`, per the strategies table. Low confidence
    and every failure path collapse to `steering` — never guess a move."""
    try:
        reply = model.complete(_DETECT_SYSTEM, [{"role": "user", "content": reply_text[:2000]}])
    except Exception:
        return STEERING
    text = (reply.text or "").strip()
    label = text.split()[0].strip(".,:;!«»\"'").lower() if text else ""
    return label if label in USER_ROLES else STEERING


@dataclass(frozen=True)
class UserMove:
    """What the writer recorded: a new open candidate, an argument, or an order."""

    role: str
    kind: str  # "hypothesis" | "argument" | "order"
    hid: str | None  # the new H-id (hypothesis) or the target (argument)
    journal_n: int


def record_user_move(
    session: Session, role: str, text: str, *, target_idea: str | None = None
) -> UserMove:
    """Record one user move in the workspace (LEDGER/IDEAS only — never DOCUMENT.md).

    generate/mutate → a new `[Hn][open] … — born_from: user` candidate (+ IDEAS entry);
    deepen/oppose with a known target → a ЗА/ПРОТИ bullet under `### <target>`;
    evaluate/weave → a journal-only order for the corresponding agent move."""
    if role not in USER_ROLES:
        raise ValueError(f"unknown user role: {role!r} (steering records nothing)")
    text = " ".join(text.split())  # workspace lines are single-line
    if not text:
        raise ValueError("empty user contribution")

    raw = (
        session.ledger_file.read_text(encoding="utf-8")
        if session.ledger_file.exists()
        else _EMPTY_LEDGER
    )
    ledger = parse_ledger(raw)  # validates before we touch anything
    n = max((r.n for r in ledger.runs), default=0) + 1

    if role in _ORDERS:
        raw = _append_to_section(
            raw, "Прогони", [f"- {n}: {role}(користувач) → замовлення: {text}"]
        )
        _write_ledger(session, raw)
        return UserMove(role=role, kind="order", hid=None, journal_n=n)

    if role in ("deepen", "oppose") and target_idea and target_idea in ledger.ids():
        side = "ЗА" if role == "deepen" else "ПРОТИ"
        raw = _append_argument(raw, target_idea, f"- {side}: {text}")
        what = "матеріал" if role == "deepen" else "контраргумент"
        raw = _append_to_section(
            raw, "Прогони", [f"- {n}: {role}(користувач) → {target_idea} {what}"]
        )
        _write_ledger(session, raw)
        return UserMove(role=role, kind="argument", hid=target_idea, journal_n=n)

    # a contribution becomes an open candidate — the source gate: NEVER a verdict,
    # whatever the user's own confidence sounds like
    hid = ledger.next_id()
    row = f"- [{hid}][open] {text} — born_from: user"
    if role == "mutate" and target_idea and target_idea in ledger.ids():
        row += f" — parents: {target_idea}"
    raw = _append_to_section(raw, "Гіпотези", [row])
    raw = _append_to_section(raw, "Прогони", [f"- {n}: {role}(користувач) → {hid}"])
    _write_ledger(session, raw)
    _append_idea(session, text)
    return UserMove(role=role, kind="hypothesis", hid=hid, journal_n=n)


def _write_ledger(session: Session, raw: str) -> None:
    parse_ledger(raw)  # the pinned v2 format must still parse — fail loudly, write nothing
    session.output_dir.mkdir(parents=True, exist_ok=True)
    session.ledger_file.write_text(raw, encoding="utf-8")


def _append_idea(session: Session, text: str) -> None:
    f = session.output_dir / "IDEAS.md"
    base = f.read_text(encoding="utf-8") if f.exists() else "# IDEAS\n"
    if not base.endswith("\n"):
        base += "\n"
    f.write_text(base + f"- {text} — born_from: user\n", encoding="utf-8")


def _section_bounds(lines: list[str], section: str) -> tuple[int, int] | None:
    """(heading_index, end_index) of `## <section>`; end excludes trailing blank lines."""
    start = next((i for i, ln in enumerate(lines) if ln.strip() == f"## {section}"), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    while end - 1 > start and not lines[end - 1].strip():
        end -= 1
    return start, end


def _append_to_section(text: str, section: str, new_lines: list[str]) -> str:
    """Append lines at the end of `## <section>`, creating the section (before the dry
    counter) when absent."""
    lines = text.splitlines()
    bounds = _section_bounds(lines, section)
    if bounds is None:
        dry = next(
            (i for i, ln in enumerate(lines) if ln.startswith("## Сухі прогони")), len(lines)
        )
        lines[dry:dry] = [f"## {section}", *new_lines, ""]
    else:
        _, end = bounds
        lines[end:end] = new_lines
    return "\n".join(lines) + "\n"


def _append_argument(text: str, hid: str, bullet: str) -> str:
    """Append a за/проти bullet under `### <hid>` in `## Аргументи` (creating either)."""
    lines = text.splitlines()
    bounds = _section_bounds(lines, "Аргументи")
    if bounds is None:
        return _append_to_section(text, "Аргументи", [f"### {hid}", bullet])
    start, end = bounds
    head = next(
        (i for i in range(start + 1, end) if lines[i].strip() == f"### {hid}"),
        None,
    )
    if head is None:
        lines[end:end] = [f"### {hid}", bullet]
    else:
        sub_end = next(
            (i for i in range(head + 1, end) if lines[i].strip().startswith("### ")), end
        )
        while sub_end - 1 > head and not lines[sub_end - 1].strip():
            sub_end -= 1
        lines[sub_end:sub_end] = [bullet]
    return "\n".join(lines) + "\n"


__all__ = [
    "STEERING",
    "USER_ROLES",
    "UserMove",
    "detect_role",
    "record_user_move",
]
