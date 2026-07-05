"""murari — the style engine.

Executes a style (a sequence of role moves) over a session: selects targets, picks mutation
types and combine partners (seeded, deterministic), enforces budgets, records per-move dry-run,
guards DOCUMENT.md ownership (only `weave` may write it), and applies the rule-based deviation
when the session goes dry. Deterministic Python — not a model decision.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

from murari.config import Config
from murari.contract import ROLES
from murari.ledger import Ledger, is_dry, parse_ledger
from murari.runner import AgentRunner, RunRequest

STYLES: dict[str, tuple[str, ...]] = {
    # Ф=generate С=evaluate Д=deepen О=oppose А=mutate Т=weave
    "explore": ("generate", "generate", "evaluate", "generate", "evaluate", "weave"),
    "debate": ("deepen", "oppose", "deepen", "oppose", "evaluate", "weave"),
    "riff": ("deepen", "mutate", "generate", "mutate", "evaluate", "weave"),
    "investigate": ("generate", "evaluate", "deepen", "evaluate", "oppose", "weave"),
    "evolve": ("generate", "evaluate", "mutate", "evaluate", "mutate", "weave"),
    "premortem": ("oppose", "oppose", "deepen", "evaluate", "weave"),
}
DEFAULT_STYLE = "investigate"

_TARGET_MOVES = ("deepen", "oppose", "mutate")
_MUTATION_CHOICES = ("scale", "invert", "transfer", "combine", "analogy")
# Per-move budget profiles (architecture.md §Budgets): generate/mutate/weave cheap,
# evaluate/oppose medium, deepen expensive.
_BUDGET_TIER = {
    "generate": "cheap",
    "mutate": "cheap",
    "weave": "cheap",
    "evaluate": "medium",
    "oppose": "medium",
    "deepen": "expensive",
}
_EMPTY_LEDGER = "# LEDGER\n\n## Гіпотези\n\n## Прогони\n\n## Сухі прогони поспіль: 0\n"


class EngineError(RuntimeError):
    """Raised on an invariant violation (e.g. a non-weave move touched DOCUMENT.md)."""


@dataclass(frozen=True)
class MoveLog:
    index: int
    move: str
    target: str | None
    mutation_type: str | None
    dry: bool
    budget_tier: str
    deviated: str | None = None  # justification when the planned move was swapped


@dataclass(frozen=True)
class EngineResult:
    style: str
    seed: int
    moves: list[MoveLog] = field(default_factory=list)
    stopped: str = "completed"  # "completed" | "budget"


def _empty() -> Ledger:
    return parse_ledger(_EMPTY_LEDGER)


def select_target(move: str, ledger: Ledger) -> str | None:
    """Deepen/oppose/mutate act on the strongest relevant hypothesis (survivors first)."""
    if move not in _TARGET_MOVES:
        return None
    pool = ledger.survivors() or list(ledger.hypotheses)
    strongest = ledger.strongest(pool)
    return strongest.id if strongest else None


def select_partner(ledger: Ledger, exclude: str | None) -> str | None:
    """The second parent for a combine mutation: the strongest OTHER survivor."""
    pool = [h for h in ledger.survivors() if h.id != exclude]
    pool = pool or [h for h in ledger.hypotheses if h.id != exclude]
    strongest = ledger.strongest(pool)
    return strongest.id if strongest else None


def pick_mutation(rng: random.Random) -> str:
    return rng.choice(_MUTATION_CHOICES)


def next_move(
    planned: str, dry_streak: int, suggested: str | None, ledger: Ledger
) -> tuple[str, str | None]:
    """Rule-based deviation: after 2 dry moves, swap to the agent's suggested role (if valid),
    else inject fresh material (mutate survivors, else generate). Returns (move, justification)."""
    if dry_streak < 2:
        return planned, None
    if suggested in ROLES:
        chosen, why = suggested, "agent-suggested"
    else:
        chosen, why = ("mutate" if ledger.survivors() else "generate"), "fallback"
    return chosen, f"{dry_streak} dry moves — deviating {planned}→{chosen} ({why})"


def _count_sources(session_output: Path) -> int:
    f = session_output / "SOURCES.md"
    if not f.exists():
        return 0
    lines = f.read_text(encoding="utf-8").splitlines()
    return sum(1 for ln in lines if ln.strip().startswith("- "))


def _doc_bytes(document_file: Path) -> bytes | None:
    return document_file.read_bytes() if document_file.exists() else None


class Engine:
    """Runs a style over a session via an injected AgentRunner (real or mock)."""

    def __init__(self, config: Config, runner: AgentRunner) -> None:
        self.config = config
        self.runner = runner

    def run_style(
        self, session, style: str = DEFAULT_STYLE, *, seed: int = 0, max_moves: int | None = None
    ) -> EngineResult:
        if style not in STYLES:
            raise EngineError(f"unknown style: {style!r}")
        rng = random.Random(seed)
        moves = STYLES[style]
        budget = min(self.config.runs, max_moves if max_moves is not None else self.config.runs)

        logs: list[MoveLog] = []
        dry_streak = (session.read_ledger() or _empty()).dry_streak
        suggested: str | None = None
        stopped = "completed"

        for i, planned in enumerate(moves):
            if i >= budget:
                stopped = "budget"
                break

            before = session.read_ledger() or _empty()
            move, justification = next_move(planned, dry_streak, suggested, before)
            target = select_target(move, before)
            mutation_type = pick_mutation(rng) if move == "mutate" else None
            partner = select_partner(before, target) if mutation_type == "combine" else None

            doc_before = _doc_bytes(session.document_file)
            sources_before = _count_sources(session.output_dir)

            result = self.runner.run(
                RunRequest(
                    role=move,
                    session_dir=session.path,
                    target_idea=target,
                    mutation_type=mutation_type,
                    partner_idea=partner,
                    style_step=f"{style}[{i}]",
                )
            )

            doc_after = _doc_bytes(session.document_file)
            if move != "weave" and doc_after != doc_before:
                raise EngineError(f"move {move!r} modified DOCUMENT.md — only weave may write it")

            after = session.read_ledger() or _empty()
            dry = is_dry(
                move,
                before,
                after,
                sources_added=max(0, _count_sources(session.output_dir) - sources_before),
                document_rebuilt=(move == "weave" and doc_after != doc_before),
            )
            dry_streak = dry_streak + 1 if dry else 0
            suggested = result.contract.get("next_role")
            logs.append(
                MoveLog(i, move, target, mutation_type, dry, _BUDGET_TIER[move], justification)
            )

        self._write_engine_log(session, style, seed, logs)
        return EngineResult(style=style, seed=seed, moves=logs, stopped=stopped)

    def _write_engine_log(self, session, style: str, seed: int, logs: list[MoveLog]) -> None:
        """Record style + seed + the move trace for reproducibility (an artifact, not state)."""
        session.artifacts_dir.mkdir(parents=True, exist_ok=True)
        trace = " ".join(f"{m.move}{'*' if m.dry else ''}" for m in logs)
        line = f"style={style} seed={seed} moves={len(logs)} [{trace}]\n"
        (session.artifacts_dir / "engine.log").write_text(line, encoding="utf-8")
