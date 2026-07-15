"""murari — the style engine.

Executes a style (a sequence of role moves) over a session: selects targets, picks mutation
types and combine partners (seeded, deterministic), enforces budgets, records per-move dry-run,
guards DOCUMENT.md ownership (only `weave` may write it), and applies the rule-based deviation
when the session goes dry. Deterministic Python — not a model decision.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from murari.config import Config
from murari.contract import ROLES
from murari.ledger import Ledger, LedgerError, is_dry, parse_ledger
from murari.runner import AgentRunner, RunnerError, RunRequest, Usage
from murari.session import restore_state, snapshot_state

STYLES: dict[str, tuple[str, ...]] = {
    # Ф=generate С=evaluate Д=deepen О=oppose А=mutate Т=weave
    # explore is divergent: breadth via generate+mutate, one score-only evaluate (the Суддя rates
    # every idea WITHOUT sources → `## Ранжування`), then a no-winner catalog weave that renders
    # the scores. No deepen (it narrows to one idea). See runner._SCORE_ONLY_STYLES.
    "explore": ("generate", "generate", "mutate", "generate", "evaluate", "weave"),
    "debate": ("deepen", "oppose", "deepen", "oppose", "evaluate", "weave"),
    "riff": ("deepen", "mutate", "generate", "mutate", "evaluate", "weave"),
    "investigate": ("generate", "evaluate", "deepen", "evaluate", "oppose", "weave"),
    "evolve": ("generate", "evaluate", "mutate", "evaluate", "mutate", "weave"),
    "premortem": ("oppose", "oppose", "deepen", "evaluate", "weave"),
}
DEFAULT_STYLE = "investigate"

# Depth is orthogonal to style: the style says which roles, the depth how many moves. Curated per
# style (the user's choice). full = the STYLES sequence; brief = 3 moves ending in weave (still a
# document); tiny = one signature role, no weave (a single-role response the chat can present).
DEPTHS = ("full", "brief", "tiny")
DEFAULT_DEPTH = "full"

_BRIEF: dict[str, tuple[str, ...]] = {
    "investigate": ("generate", "evaluate", "weave"),
    "explore": ("generate", "mutate", "weave"),
    "debate": ("deepen", "oppose", "weave"),
    "riff": ("deepen", "mutate", "weave"),
    "evolve": ("evaluate", "mutate", "weave"),
    "premortem": ("oppose", "deepen", "weave"),
}
_TINY: dict[str, tuple[str, ...]] = {
    "investigate": ("evaluate",),
    "explore": ("generate",),
    "debate": ("oppose",),
    "riff": ("mutate",),
    "evolve": ("mutate",),
    "premortem": ("oppose",),
}

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


def sequence_for(style: str, depth: str = DEFAULT_DEPTH) -> tuple[str, ...]:
    """The move sequence for a (style, depth). Raises EngineError on an unknown style/depth."""
    if style not in STYLES:
        raise EngineError(f"unknown style: {style!r}")
    if depth == "full":
        return STYLES[style]
    if depth == "brief":
        return _BRIEF[style]
    if depth == "tiny":
        return _TINY[style]
    raise EngineError(f"unknown depth: {depth!r}; use one of {DEPTHS}")


@dataclass(frozen=True)
class MoveLog:
    index: int
    move: str
    target: str | None
    mutation_type: str | None
    dry: bool
    budget_tier: str
    deviated: str | None = None  # justification when the planned move was swapped
    duration_s: float | None = None  # wall-clock of the move
    usage: Usage = field(default_factory=Usage)  # tokens + cost of the move


@dataclass(frozen=True)
class EngineResult:
    style: str
    seed: int
    depth: str = DEFAULT_DEPTH
    moves: list[MoveLog] = field(default_factory=list)
    stopped: str = "completed"  # "completed" | "budget" | "failed"
    duration_s: float = 0.0  # total wall-clock of the run
    usage: Usage = field(default_factory=Usage)  # totals across moves
    error: str = ""  # set when stopped == "failed" (the completed moves before it are kept)


def _fmt_k(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def _fmt_usage(u: Usage) -> str:
    return f"in {_fmt_k(u.billed_input)} out {_fmt_k(u.output_tokens)} ${u.cost_usd:.2f}"


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
        self,
        session,
        style: str = DEFAULT_STYLE,
        *,
        depth: str = DEFAULT_DEPTH,
        seed: int = 0,
        max_moves: int | None = None,
        target: str | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> EngineResult:
        moves = sequence_for(style, depth)  # validates style + depth
        if target is not None:
            ids = (session.read_ledger() or _empty()).ids()
            if target not in ids:
                raise EngineError(f"unknown target {target!r}; available: {sorted(ids) or 'none'}")
        rng = random.Random(seed)
        budget = min(self.config.runs, max_moves if max_moves is not None else self.config.runs)
        total = min(len(moves), budget)  # moves that will actually run — the "N" in "step i/N"

        logs: list[MoveLog] = []
        dry_streak = (session.read_ledger() or _empty()).dry_streak
        suggested: str | None = None
        stopped = "completed"
        error = ""
        total_usage = Usage()
        run_start = time.monotonic()
        self._progress_init(session, style, depth, seed, target, total, on_progress)

        for i, planned in enumerate(moves):
            if i >= budget:
                stopped = "budget"
                break

            # Roll back only THIS move on failure — completed moves stay committed (the ledger
            # they wrote is valid state). A killed/failed move may have left partial files.
            move_snap = snapshot_state(session)
            try:
                before = session.read_ledger() or _empty()
                move, justification = next_move(planned, dry_streak, suggested, before)
                # a user-pinned --target overrides auto-selection for deepen/oppose/mutate —
                # "research this hypothesis"; otherwise the strongest survivor is chosen.
                if target is not None and move in _TARGET_MOVES:
                    move_target = target
                else:
                    move_target = select_target(move, before)
                mutation_type = pick_mutation(rng) if move == "mutate" else None
                partner = (
                    select_partner(before, move_target) if mutation_type == "combine" else None
                )

                head = f"[{i + 1}/{total}] {move}"
                if move_target:
                    head += f" →{move_target}"
                if mutation_type:
                    head += f" [{mutation_type}]"
                self._emit(session, on_progress, f"{head} — виконую…")

                doc_before = _doc_bytes(session.document_file)
                sources_before = _count_sources(session.output_dir)

                t0 = time.monotonic()
                result = self.runner.run(
                    RunRequest(
                        role=move,
                        session_dir=session.path,
                        target_idea=move_target,
                        mutation_type=mutation_type,
                        partner_idea=partner,
                        style_step=f"{style}[{i}]",
                    )
                )
                dt = time.monotonic() - t0

                doc_after = _doc_bytes(session.document_file)
                if move != "weave" and doc_after != doc_before:
                    raise EngineError(
                        f"move {move!r} touched DOCUMENT.md — only weave may write it"
                    )

                after = session.read_ledger() or _empty()
                dry = is_dry(
                    move,
                    before,
                    after,
                    sources_added=max(0, _count_sources(session.output_dir) - sources_before),
                    document_rebuilt=(move == "weave" and doc_after != doc_before),
                )
            except (RunnerError, EngineError, LedgerError) as e:
                restore_state(session, move_snap)  # undo only the failed move; keep the rest
                stopped, error = "failed", f"{type(e).__name__}: {e}"
                self._emit(
                    session,
                    on_progress,
                    f"хід {i + 1}/{total} впав: {e} — завершені ходи збережено",
                )
                break

            dry_streak = dry_streak + 1 if dry else 0
            suggested = result.contract.get("next_role")
            total_usage = total_usage + result.usage
            verdict = "сухий" if dry else "продуктивний"
            self._emit(
                session,
                on_progress,
                f"{head} — готово за {dt:.0f}s ({verdict}) · {_fmt_usage(result.usage)}",
            )
            logs.append(
                MoveLog(
                    i,
                    move,
                    move_target,
                    mutation_type,
                    dry,
                    _BUDGET_TIER[move],
                    justification,
                    dt,
                    result.usage,
                )
            )

        run_dt = time.monotonic() - run_start
        self._emit(session, on_progress, f"разом: {run_dt:.0f}s · {_fmt_usage(total_usage)}")
        self._write_engine_log(session, style, depth, seed, logs, stopped, run_dt, total_usage)
        return EngineResult(
            style=style,
            seed=seed,
            depth=depth,
            moves=logs,
            stopped=stopped,
            duration_s=run_dt,
            usage=total_usage,
            error=error,
        )

    def _progress_init(
        self, session, style: str, depth: str, seed: int, target, total: int, on_progress
    ) -> None:
        """Start a fresh live progress log for this run (progress.log = the current run only)."""
        session.artifacts_dir.mkdir(parents=True, exist_ok=True)
        tgt = f" target={target}" if target else ""
        (session.artifacts_dir / "progress.log").write_text(
            f"# {style}/{depth} seed={seed}{tgt} — {total} ходів\n", encoding="utf-8"
        )
        self._emit(session, on_progress, f"стиль {style}/{depth}: {total} ходів")

    def _emit(self, session, on_progress, line: str) -> None:
        """Append a progress line to progress.log (live trace) and to the caller, if watching."""
        with (session.artifacts_dir / "progress.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        if on_progress is not None:
            on_progress(line)

    def _write_engine_log(
        self,
        session,
        style: str,
        depth: str,
        seed: int,
        logs: list[MoveLog],
        stopped: str,
        duration_s: float,
        usage: Usage,
    ) -> None:
        """Append one line per run to engine.log — the history of styles executed on the session,
        with total time, tokens and cost."""
        session.artifacts_dir.mkdir(parents=True, exist_ok=True)
        trace = " ".join(f"{m.move}{'*' if m.dry else ''}" for m in logs)
        line = (
            f"style={style}/{depth} seed={seed} moves={len(logs)} {stopped} "
            f"{duration_s:.0f}s in={usage.billed_input} out={usage.output_tokens} "
            f"${usage.cost_usd:.2f} [{trace}]\n"
        )
        with (session.artifacts_dir / "engine.log").open("a", encoding="utf-8") as f:
            f.write(line)
