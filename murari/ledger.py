"""murari — LEDGER v2 read side.

The agent *writes* LEDGER.md; the orchestrator *reads* it to schedule moves and enforce
budgets. Parses the hypothesis list (H-ids, statuses, source, «випробувано», lineage,
mutation), the run journal, and the dry counter; provides lineage helpers and the per-move
productivity check `is_dry`. Malformed lines raise `LedgerError` rather than being dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from murari.contract import STATUSES, VERDICTS

_HID = re.compile(r"^H\d+$")
_HYP = re.compile(r"^-\s*\[(H\d+)\]\[(\w+)\]\s+(.+)$")
_RUN = re.compile(r"^-\s*(\d+):\s*(\w+)\((.*?)\)\s*→\s*(.*)$")
_DRY = re.compile(r"^##\s*Сухі прогони поспіль:\s*(\d+)\s*$", re.M)
_FIELD = re.compile(r"^(джерело|випробувано|parents|mutation|примітка):\s*(.*)$")
_EXECUTORS = ("агент", "користувач")

# Verdict strength for target selection (strongest-first): confirmed > partial > open > refuted.
_VERDICT_RANK = {"confirmed": 3, "partial": 2, "open": 1, "refuted": 0}


class LedgerError(ValueError):
    """Raised when LEDGER.md cannot be parsed as v2."""


@dataclass(frozen=True)
class Hypothesis:
    id: str
    status: str
    text: str
    source: str | None = None
    parents: tuple[str, ...] = ()
    mutation: str | None = None
    tested: int = 0
    note: str | None = None

    @property
    def strength(self) -> tuple[int, int]:
        return (_VERDICT_RANK[self.status], self.tested)


@dataclass(frozen=True)
class RunEntry:
    n: int
    move: str
    executor: str  # "агент" | "користувач"
    produced: str  # raw text after → (e.g. "H1..H5" or "H1 confirmed, H2 refuted")
    raw: str


@dataclass(frozen=True)
class Ledger:
    hypotheses: tuple[Hypothesis, ...] = ()
    runs: tuple[RunEntry, ...] = ()
    dry_streak: int = 0
    _by_id: dict[str, Hypothesis] = field(default_factory=dict, compare=False, repr=False)

    def by_id(self, hid: str) -> Hypothesis | None:
        return self._by_id.get(hid)

    def ids(self) -> set[str]:
        return set(self._by_id)

    def next_id(self) -> str:
        nums = [int(h.id[1:]) for h in self.hypotheses]
        return f"H{(max(nums) + 1) if nums else 1}"

    def descendants(self, hid: str) -> list[Hypothesis]:
        """All hypotheses reachable via `parents` back to `hid` (transitive)."""
        out: list[Hypothesis] = []
        frontier = {hid}
        changed = True
        while changed:
            changed = False
            for h in self.hypotheses:
                if h in out:
                    continue
                if frontier & set(h.parents):
                    out.append(h)
                    frontier.add(h.id)
                    changed = True
        return out

    def survivors(self) -> list[Hypothesis]:
        """Hypotheses fit to mutate/evolve — confirmed or partial verdicts."""
        return [h for h in self.hypotheses if h.status in ("confirmed", "partial")]

    def strongest(self, candidates: list[Hypothesis] | None = None) -> Hypothesis | None:
        """The strongest hypothesis (verdict rank, then «випробувано») — for target/combine."""
        pool = self.hypotheses if candidates is None else candidates
        return max(pool, default=None, key=lambda h: h.strength)


def _make(hyps: list[Hypothesis], runs: list[RunEntry], dry: int) -> Ledger:
    return Ledger(
        hypotheses=tuple(hyps),
        runs=tuple(runs),
        dry_streak=dry,
        _by_id={h.id: h for h in hyps},
    )


def _sections(text: str) -> dict[str, list[str]]:
    """Split into `## <title>` sections → the lines under each (excluding the heading)."""
    out: dict[str, list[str]] = {}
    cur: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            cur = line[3:].split(":", 1)[0].strip()
            out.setdefault(cur, [])
        elif cur is not None:
            out[cur].append(line)
    return out


def _parse_hyp_rest(rest: str) -> tuple[str, dict[str, str]]:
    parts = rest.split(" — ")
    text_parts = [parts[0]]
    fields: dict[str, str] = {}
    for seg in parts[1:]:
        m = _FIELD.match(seg)
        if m:
            fields[m.group(1)] = m.group(2).strip()
        else:
            text_parts.append(seg)  # an em-dash inside the hypothesis text
    return " — ".join(text_parts).strip(), fields


def _parse_parents(value: str) -> tuple[str, ...]:
    parents = tuple(p.strip() for p in value.split("+") if p.strip())
    for p in parents:
        if not _HID.match(p):
            raise LedgerError(f"bad parent id: {p!r}")
    return parents


def _parse_hypothesis(line: str) -> Hypothesis:
    m = _HYP.match(line)
    if not m:
        raise LedgerError(f"malformed hypothesis line: {line!r}")
    hid, status, rest = m.group(1), m.group(2), m.group(3)
    if status not in STATUSES:
        raise LedgerError(f"bad status {status!r} in {line!r}")
    text, f = _parse_hyp_rest(rest)
    tested = 0
    if "випробувано" in f:
        try:
            tested = int(f["випробувано"])
        except ValueError as e:
            raise LedgerError(f"bad «випробувано» in {line!r}") from e
    return Hypothesis(
        id=hid,
        status=status,
        text=text,
        source=f.get("джерело"),
        parents=_parse_parents(f["parents"]) if "parents" in f else (),
        mutation=f.get("mutation"),
        tested=tested,
        note=f.get("примітка"),
    )


def _parse_run(line: str) -> RunEntry:
    m = _RUN.match(line)
    if not m:
        raise LedgerError(f"malformed run-journal line: {line!r}")
    tokens = [t.strip() for t in m.group(3).split(",") if t.strip()]
    executor = tokens[-1] if tokens and tokens[-1] in _EXECUTORS else "агент"
    return RunEntry(
        n=int(m.group(1)),
        move=m.group(2),
        executor=executor,
        produced=m.group(4).strip(),
        raw=line,
    )


def parse_ledger(text: str) -> Ledger:
    """Parse LEDGER.md (v2) into a `Ledger`. Raises `LedgerError` on a malformed line or a
    missing dry counter."""
    if not text.lstrip().startswith("# LEDGER"):
        raise LedgerError("LEDGER.md must start with '# LEDGER'")
    sections = _sections(text)

    hyps = [
        _parse_hypothesis(ln) for ln in sections.get("Гіпотези", []) if ln.strip().startswith("- ")
    ]
    seen: set[str] = set()
    for h in hyps:
        if h.id in seen:
            raise LedgerError(f"duplicate hypothesis id: {h.id}")
        seen.add(h.id)

    runs = [_parse_run(ln) for ln in sections.get("Прогони", []) if ln.strip().startswith("- ")]

    m = _DRY.search(text)
    if not m:
        raise LedgerError("missing 'Сухі прогони поспіль: N' counter")
    return _make(hyps, runs, int(m.group(1)))


# --- Per-move productivity ---------------------------------------------------


def _new_ids(before: Ledger, after: Ledger) -> int:
    b = before.ids()
    return sum(1 for h in after.hypotheses if h.id not in b)


def _newly_verdicted(before: Ledger, after: Ledger) -> int:
    count = 0
    for h in after.hypotheses:
        if h.status in VERDICTS and h.source:
            prev = before.by_id(h.id)
            if prev is None or prev.status not in VERDICTS:
                count += 1
    return count


def is_productive(
    move: str,
    before: Ledger,
    after: Ledger,
    *,
    sources_added: int = 0,
    document_rebuilt: bool = False,
) -> bool:
    """Whether a move produced enough to not be dry (thresholds from strategies.md).

    Ledger-derivable moves use `before`/`after`; `deepen`/`oppose` need `sources_added`
    (from the SOURCES.md delta) and `weave` needs `document_rebuilt` (from the engine)."""
    if move == "generate":
        return _new_ids(before, after) >= 3
    if move == "evaluate":
        return _newly_verdicted(before, after) >= 1
    if move == "deepen":
        return sources_added >= 2
    if move == "oppose":
        return sources_added >= 1
    if move == "mutate":
        return _new_ids(before, after) >= 1
    if move == "weave":
        return document_rebuilt
    raise LedgerError(f"unknown move: {move!r}")


def is_dry(move: str, before: Ledger, after: Ledger, **kw: object) -> bool:
    return not is_productive(move, before, after, **kw)  # type: ignore[arg-type]
