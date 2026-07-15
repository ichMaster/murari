"""MUR-011 — the style engine: style tables, target/partner/mutation selection, the dry-run
deviation rule, and a full mocked style run (workspace deltas, budgets, DOCUMENT ownership).

No real `claude`: the engine is driven by MockAgentRunner + the scripted FakeAgent (conftest).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from murari.config import Config
from murari.contract import GENERATIVE_ROLES, ROLES
from murari.engine import (
    DEFAULT_STYLE,
    STYLES,
    Engine,
    EngineError,
    next_move,
    pick_mutation,
    select_partner,
    select_target,
    sequence_for,
)
from murari.ledger import parse_ledger
from murari.runner import MockAgentRunner, RunRequest
from murari.session import Session, create_session, open_session

FIX = Path(__file__).parent / "fixtures" / "contract-v2"
_ALL_ROLES = ("generate", "evaluate", "deepen", "oppose", "mutate", "weave")


def _contracts() -> dict:
    return {r: json.loads((FIX / f"{r}.json").read_text(encoding="utf-8")) for r in _ALL_ROLES}


def _cfg(tmp_path, runs: int = 6) -> Config:
    return Config(runs=runs, max_turns=15, model="m", home=tmp_path)


_LEDGER = (
    "# LEDGER\n\n## Гіпотези\n"
    "- [H1][confirmed] a — джерело: https://e.com/a — випробувано: 2\n"
    "- [H3][partial] c — джерело: https://e.com/c\n"
    "- [H4][open] d\n\n## Прогони\n\n## Сухі прогони поспіль: 0\n"
)


# --- style tables ---


def test_default_style_is_investigate():
    assert DEFAULT_STYLE == "investigate" and DEFAULT_STYLE in STYLES


def test_every_style_ends_in_weave_and_uses_known_roles():
    for name, seq in STYLES.items():
        assert seq[-1] == "weave", f"{name} must end in weave"
        assert all(m in ROLES for m in seq), f"{name} has an unknown move"


def test_only_weave_appears_once_at_the_end():
    # weave is the single document-writing move; it must not appear mid-sequence
    for name, seq in STYLES.items():
        assert seq.count("weave") == 1, f"{name} weaves more than once"


# --- depth (full / brief / tiny) ---


def test_sequence_for_full_is_the_style():
    assert sequence_for("investigate", "full") == STYLES["investigate"]
    assert sequence_for("explore", "brief") == ("generate", "mutate", "weave")  # user's Ф→А→Т
    assert sequence_for("debate", "tiny") == ("oppose",)


def test_brief_is_three_ending_in_weave_tiny_is_one_role():
    for style in STYLES:
        brief = sequence_for(style, "brief")
        assert len(brief) == 3 and brief[-1] == "weave"  # brief still writes a document
        tiny = sequence_for(style, "tiny")
        assert len(tiny) == 1 and tiny[0] != "weave"  # one role, no weave


def test_sequence_for_unknown_depth_raises():
    with pytest.raises(EngineError, match="unknown depth"):
        sequence_for("investigate", "huge")


def test_run_style_brief_runs_three_moves(tmp_path, fake_agent_cls):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема")
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    res = Engine(cfg, mock).run_style(session, "investigate", depth="brief", seed=0)
    assert [m.move for m in res.moves] == ["generate", "evaluate", "weave"]
    assert res.depth == "brief" and session.read_document() is not None


def test_run_style_tiny_is_one_role_no_document(tmp_path, fake_agent_cls):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема")
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    res = Engine(cfg, mock).run_style(session, "explore", depth="tiny", seed=0)
    assert [m.move for m in res.moves] == ["generate"]  # a single role
    assert session.read_document() is None  # tiny doesn't weave


def test_explore_is_divergent():
    # explore surfaces many ideas (generate+mutate), scores them once (score-only evaluate),
    # then catalogs; it must not deepen (that narrows to a single idea)
    seq = STYLES["explore"]
    assert seq == ("generate", "generate", "mutate", "generate", "evaluate", "weave")
    assert "deepen" not in seq


# --- target / partner / mutation selection ---


def test_select_target_none_for_generative_and_evaluate():
    led = parse_ledger(_LEDGER)
    assert select_target("generate", led) is None
    assert select_target("evaluate", led) is None
    assert select_target("weave", led) is None


def test_select_target_picks_strongest_survivor():
    led = parse_ledger(_LEDGER)
    assert select_target("deepen", led) == "H1"  # confirmed+tested beats partial and open
    assert select_target("oppose", led) == "H1"
    assert select_target("mutate", led) == "H1"


def test_select_target_falls_back_to_any_hypothesis_when_no_survivors():
    led = parse_ledger(
        "# LEDGER\n\n## Гіпотези\n- [H4][open] d\n- [H5][open] e\n\n"
        "## Прогони\n\n## Сухі прогони поспіль: 0\n"
    )
    assert select_target("deepen", led) in {"H4", "H5"}


def test_select_partner_excludes_target():
    led = parse_ledger(_LEDGER)
    assert select_partner(led, exclude="H1") == "H3"  # strongest of the remainder


def test_select_partner_none_when_alone():
    led = parse_ledger(
        "# LEDGER\n\n## Гіпотези\n- [H1][confirmed] a — джерело: https://e.com/a\n\n"
        "## Прогони\n\n## Сухі прогони поспіль: 0\n"
    )
    assert select_partner(led, exclude="H1") is None


def test_pick_mutation_is_seeded_and_in_range():
    a = [pick_mutation(random.Random(7)) for _ in range(3)]
    b = [pick_mutation(random.Random(7)) for _ in range(3)]
    assert a == b  # deterministic per seed
    assert all(m in {"scale", "invert", "transfer", "combine", "analogy"} for m in a)


# --- the dry-run deviation rule ---


def test_next_move_no_deviation_below_threshold():
    led = parse_ledger(_LEDGER)
    move, why = next_move("evaluate", dry_streak=1, suggested="oppose", ledger=led)
    assert move == "evaluate" and why is None


def test_next_move_deviates_to_agent_suggestion_after_two_dry():
    led = parse_ledger(_LEDGER)
    move, why = next_move("evaluate", dry_streak=2, suggested="oppose", ledger=led)
    assert move == "oppose" and why and "agent-suggested" in why


def test_next_move_fallback_mutate_when_survivors_exist():
    led = parse_ledger(_LEDGER)  # has survivors
    move, why = next_move("evaluate", dry_streak=2, suggested=None, ledger=led)
    assert move == "mutate" and "fallback" in why


def test_next_move_fallback_generate_when_no_survivors():
    led = parse_ledger("# LEDGER\n\n## Гіпотези\n\n## Прогони\n\n## Сухі прогони поспіль: 0\n")
    move, why = next_move("evaluate", dry_streak=3, suggested="planner", ledger=led)
    assert move == "generate" and "fallback" in why  # 'planner' isn't a real role → fallback


# --- full mocked style run ---


def test_run_style_happy_path(tmp_path, fake_agent_cls):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема")
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    res = Engine(cfg, mock).run_style(session, "investigate", seed=0)

    assert res.stopped == "completed"
    assert [m.move for m in res.moves] == list(STYLES["investigate"])
    assert [c.role for c in mock.calls] == list(STYLES["investigate"])
    assert not any(m.dry for m in res.moves)  # the scripted agent is productive every move
    assert session.read_document() is not None  # weave wrote it
    led = session.read_ledger()
    assert led is not None and len(led.hypotheses) == 3


def test_run_style_respects_run_budget(tmp_path, fake_agent_cls):
    cfg = _cfg(tmp_path, runs=3)  # fewer runs than the 6-move style
    session = create_session(cfg, "тема")
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    res = Engine(cfg, mock).run_style(session, "investigate", seed=0)

    assert res.stopped == "budget"
    assert len(res.moves) == 3
    assert [c.role for c in mock.calls] == ["generate", "evaluate", "deepen"]
    assert session.read_document() is None  # weave never reached


def test_run_style_combine_passes_partner(tmp_path, fake_agent_cls):
    # a seed whose first mutation roll is `combine`
    seed = next(s for s in range(500) if pick_mutation(random.Random(s)) == "combine")
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема")
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    Engine(cfg, mock).run_style(session, "evolve", seed=seed)

    first_mutate = next(c for c in mock.calls if c.role == "mutate")
    assert first_mutate.mutation_type == "combine"
    assert first_mutate.target_idea == "H1"  # the confirmed survivor
    assert first_mutate.partner_idea == "H2"  # the strongest of the remainder


def test_run_style_document_guard_rejects_non_weave_write(tmp_path):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема")

    empty = "# LEDGER\n\n## Гіпотези\n\n## Прогони\n\n## Сухі прогони поспіль: 0\n"

    def _sneaky(req: RunRequest) -> None:
        s = Session(req.session_dir)
        s.ledger_file.write_text(empty, encoding="utf-8")
        if req.role == "generate":
            s.document_file.write_text("sneaky non-weave write\n", encoding="utf-8")

    mock = MockAgentRunner(_contracts(), on_run=_sneaky)
    res = Engine(cfg, mock).run_style(session, "explore", seed=0)
    # the guard stops the run gracefully (no raise) and reports it; completed moves are kept
    assert res.stopped == "failed" and "DOCUMENT" in res.error
    assert res.moves == []  # failed on the very first move → nothing completed


def test_run_style_deviates_after_two_dry_moves(tmp_path):
    # a "dead" agent: writes only an empty ledger, never any hypotheses/sources/document,
    # and never suggests a next_role → every move is dry, and the fallback deviation fires.
    dead = json.loads((FIX / "generate.json").read_text(encoding="utf-8"))
    dead["hypotheses"] = []
    dead["next_role"] = None
    empty = "# LEDGER\n\n## Гіпотези\n\n## Прогони\n\n## Сухі прогони поспіль: 0\n"

    def _dead_run(req: RunRequest) -> None:
        Session(req.session_dir).ledger_file.write_text(empty, encoding="utf-8")

    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема")
    mock = MockAgentRunner({"generate": dead}, on_run=_dead_run)
    res = Engine(cfg, mock).run_style(session, "explore", seed=0)

    assert all(m.dry for m in res.moves)  # nothing productive
    assert res.moves[0].deviated is None and res.moves[1].deviated is None  # streak < 2
    assert res.moves[2].deviated is not None  # third move: 2 dry in a row → deviate
    assert res.moves[2].move == "generate"  # fallback (no survivors, no suggestion)


def test_open_and_continue_grows_the_same_workspace(tmp_path, fake_agent_cls):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема")
    agent = fake_agent_cls()  # one stateful agent across both runs
    mock = MockAgentRunner(_contracts(), on_run=agent)

    Engine(cfg, mock).run_style(session, "investigate", seed=0)
    first = len(session.read_ledger().hypotheses)

    # reopen the same directory and continue with a different style
    reopened = open_session(session.path)
    Engine(cfg, mock).run_style(reopened, "evolve", seed=1)

    assert len(reopened.read_ledger().hypotheses) > first  # ledger grew, not reset
    assert reopened.read_document() is not None  # document still present after continue


def test_run_style_target_pins_target_moves(tmp_path, fake_agent_cls):
    # seed the ledger with hypotheses, then pin debate's deepen/oppose to a chosen H
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема")
    agent = fake_agent_cls()
    mock = MockAgentRunner(_contracts(), on_run=agent)
    Engine(cfg, mock).run_style(session, "explore", seed=0, max_moves=1)  # one generate → H1..H3

    mock.calls.clear()
    Engine(cfg, mock).run_style(session, "debate", seed=0, target="H2")
    for c in mock.calls:
        if c.role in ("deepen", "oppose", "mutate"):
            assert c.target_idea == "H2"  # user target wins over auto-selection


def test_run_style_unknown_target_raises(tmp_path, fake_agent_cls):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема")
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    Engine(cfg, mock).run_style(session, "explore", seed=0, max_moves=1)  # H1..H3 exist
    with pytest.raises(EngineError, match="unknown target"):
        Engine(cfg, mock).run_style(session, "debate", target="H99")


def test_run_style_keeps_completed_moves_on_failure(tmp_path, fake_agent_cls):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема")
    # contracts for the first two moves only → investigate's 3rd move (deepen) raises RunnerError
    partial = {k: _contracts()[k] for k in ("generate", "evaluate")}
    mock = MockAgentRunner(partial, on_run=fake_agent_cls())
    res = Engine(cfg, mock).run_style(session, "investigate", seed=0)

    assert res.stopped == "failed" and "RunnerError" in res.error
    assert [m.move for m in res.moves] == ["generate", "evaluate"]  # completed moves kept
    led = session.read_ledger()
    assert led is not None and len(led.hypotheses) == 3  # generate's work survived the failure


def test_run_style_unknown_style_raises(tmp_path, fake_agent_cls):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема")
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    with pytest.raises(EngineError, match="unknown style"):
        Engine(cfg, mock).run_style(session, "nope")


def test_run_style_writes_engine_log(tmp_path, fake_agent_cls):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема")
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    Engine(cfg, mock).run_style(session, "investigate", seed=42)

    log = (session.artifacts_dir / "engine.log").read_text(encoding="utf-8")
    assert "style=investigate" in log and "seed=42" in log


def test_run_style_emits_live_progress(tmp_path, fake_agent_cls):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема")
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    lines: list[str] = []
    Engine(cfg, mock).run_style(session, "investigate", seed=0, on_progress=lines.append)

    # a start + a done line per move, numbered "step i/N of 6"
    assert any(ln.startswith("[1/6] generate — виконую") for ln in lines)
    assert any("[6/6] weave" in ln and "готово за" in ln for ln in lines)
    # and persisted live to progress.log
    prog = (session.artifacts_dir / "progress.log").read_text(encoding="utf-8")
    assert "[1/6] generate" in prog and "[6/6] weave" in prog


def test_progress_log_resets_per_run(tmp_path, fake_agent_cls):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема")
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    Engine(cfg, mock).run_style(session, "explore", seed=0, max_moves=2)  # 2-move run
    prog = (session.artifacts_dir / "progress.log").read_text(encoding="utf-8")
    assert prog.count("виконую") == 2  # only the current run's moves, not accumulated


def test_run_style_aggregates_usage_and_time(tmp_path, fake_agent_cls):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема")
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())  # 100 in / 20 out / $0.01 a move
    res = Engine(cfg, mock).run_style(session, "investigate", seed=0)  # 6 moves

    assert res.usage.billed_input == 600  # 6 × 100
    assert res.usage.output_tokens == 120  # 6 × 20
    assert abs(res.usage.cost_usd - 0.06) < 1e-9
    # totals persisted to engine.log; per-move + total in progress.log
    log = (session.artifacts_dir / "engine.log").read_text(encoding="utf-8")
    assert "in=600" in log and "out=120" in log and "$0.06" in log
    prog = (session.artifacts_dir / "progress.log").read_text(encoding="utf-8")
    assert "in 100 out 20 $0.01" in prog and "разом:" in prog


def test_engine_log_accumulates_style_history(tmp_path, fake_agent_cls):
    cfg = _cfg(tmp_path)
    session = create_session(cfg, "тема")
    mock = MockAgentRunner(_contracts(), on_run=fake_agent_cls())
    Engine(cfg, mock).run_style(session, "investigate", seed=0)
    Engine(cfg, mock).run_style(session, "explore", seed=1)

    log = (session.artifacts_dir / "engine.log").read_text(encoding="utf-8").strip()
    assert "style=investigate" in log and "style=explore" in log
    assert len(log.splitlines()) == 2  # one line per run — the styles executed on this session


def test_generative_roles_constant_matches_no_web_moves():
    # sanity: the generative set the source-gate keys on is exactly generate+mutate
    assert GENERATIVE_ROLES == {"generate", "mutate"}
