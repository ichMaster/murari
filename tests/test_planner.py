"""MUR-015 — the move planner: complementarity, debate pairing, style selection.

Pure logic over constructed ledgers + MockHaikuModel for style inference — no paid calls.
"""

from __future__ import annotations

import pytest

from murari.engine import STYLES, EngineResult, MoveLog
from murari.haiku import HaikuError, HaikuReply, MockHaikuModel
from murari.ledger import parse_ledger
from murari.participant import STEERING
from murari.planner import PlannedMove, choose_style, deviation_notes, plan_next_move

_CONTRIBUTIONS = ("generate", "deepen", "oppose", "mutate")


def _ledger(*rows: str, dry: int = 0):
    body = "\n".join(rows)
    return parse_ledger(
        f"# LEDGER\n\n## Гіпотези\n{body}\n\n## Прогони\n\n## Сухі прогони поспіль: {dry}\n"
    )


_MIXED = _ledger(
    "- [H1][confirmed] сильна ідея — джерело: https://e.com/1 — випробувано: 2",
    "- [H2][open] відкрита ідея",
    "- [H3][partial] частково — джерело: https://e.com/2",
)
_EMPTY = _ledger()


# --- complementarity (never the user's role, except debate) ---


def test_complementarity_matrix_never_duplicates_user_role():
    for style in STYLES:
        if style == "debate":
            continue
        for user_role in _CONTRIBUTIONS:
            planned = plan_next_move(style, _MIXED, user_role)
            assert planned.role != user_role, (style, user_role)


def test_opposing_user_favors_deepen_or_evaluate():
    for style in ("investigate", "premortem", "debate"):
        planned = plan_next_move(style, _MIXED, "oppose")
        assert planned.role in ("deepen", "evaluate"), style


def test_steering_plans_by_ledger_state():
    # open hypotheses exist → investigate wants the Суддя, premortem the Опонент
    assert plan_next_move("investigate", _MIXED, STEERING).role == "evaluate"
    assert plan_next_move("premortem", _MIXED, STEERING).role == "oppose"
    # nothing open → breadth again
    verdicted = _ledger("- [H1][refuted] закрита — джерело: https://e.com/x")
    assert plan_next_move("investigate", verdicted, STEERING).role == "generate"


def test_empty_ledger_starts_with_ideas():
    planned = plan_next_move("investigate", _EMPTY, STEERING)
    assert planned.role == "generate" and planned.target is None


def test_target_reuses_strongest_survivor_rules():
    planned = plan_next_move("premortem", _MIXED, STEERING)
    assert planned.role == "oppose" and planned.target == "H1"  # strongest survivor


# --- debate: adversarial pairing, no winner ---


def test_debate_pairs_against_the_user_side():
    attacks = plan_next_move("debate", _MIXED, "oppose")
    assert attacks.role == "deepen"  # user attacks → agent defends with evidence
    defends = plan_next_move("debate", _MIXED, "deepen")
    assert defends.role == "oppose"  # user defends → agent attacks
    fantasizes = plan_next_move("debate", _MIXED, "generate")
    assert fantasizes.role == "oppose"


def test_debate_sides_can_swap():
    first = plan_next_move("debate", _MIXED, "deepen")
    swapped = plan_next_move("debate", _MIXED, "oppose")
    assert (first.role, swapped.role) == ("oppose", "deepen")


def test_planner_never_declares_a_winner():
    for user_role in (*_CONTRIBUTIONS, STEERING):
        for style in STYLES:
            note = plan_next_move(style, _MIXED, user_role).note.lower()
            # the only permitted mention of a winner is the explicit "there is none"
            assert "виграв" not in note, (style, user_role)
            assert "перемож" not in note.replace("переможця немає", ""), (style, user_role)
    assert "переможця немає" in plan_next_move("debate", _MIXED, "deepen").note


# --- orders map straight to the agent move ---


def test_user_orders_plan_that_exact_move():
    assert plan_next_move("investigate", _MIXED, "evaluate").role == "evaluate"
    weave_order = plan_next_move("explore", _MIXED, "weave")
    assert weave_order.role == "weave" and "замовлення" in weave_order.note


def test_unknown_style_raises():
    with pytest.raises(ValueError, match="unknown style"):
        plan_next_move("bogus", _MIXED, STEERING)


# --- style selection ---


def test_explicit_style_wins_without_model_call():
    mock = MockHaikuModel([HaikuReply(text="explore")])
    assert choose_style("debate", mock, "будь-яка тема") == "debate"
    assert mock.calls == []  # explicit /style never asks the model


def test_explicit_unknown_style_raises():
    with pytest.raises(ValueError, match="unknown style"):
        choose_style("bogus")


@pytest.mark.parametrize(
    ("framing", "label", "expected"),
    [
        ("накидай варіантів, як назвати продукт", "explore", "explore"),
        ("чи правда, що X більше за Y?", "investigate", "investigate"),
        ("посперечаймось: X краще за Y", "debate", "debate"),
    ],
)
def test_inference_maps_framings(framing, label, expected):
    mock = MockHaikuModel([HaikuReply(text=label)])
    assert choose_style(None, mock, framing) == expected


def test_inference_falls_back_to_investigate():
    assert choose_style(None, MockHaikuModel([HaikuReply(text="галюн")]), "тема") == "investigate"
    assert choose_style(None, MockHaikuModel([HaikuError("down")]), "тема") == "investigate"
    assert choose_style(None, None, "тема") == "investigate"
    assert choose_style(None, MockHaikuModel(), "") == "investigate"  # blank topic, no call


def test_mid_session_change_replans_from_new_template():
    # same state, different style → a different planned move (the template drives the plan)
    before = plan_next_move(choose_style("investigate"), _MIXED, STEERING)
    after = plan_next_move(choose_style("premortem"), _MIXED, STEERING)
    assert (before.role, after.role) == ("evaluate", "oppose")


# --- deviation stays the engine's rule; the planner only surfaces it ---


def test_deviation_notes_surface_engine_justifications():
    res = EngineResult(
        style="investigate",
        seed=0,
        moves=[
            MoveLog(0, "generate", None, None, False, "cheap"),
            MoveLog(1, "mutate", "H1", "invert", False, "cheap", "2 dry moves — deviating"),
        ],
    )
    assert deviation_notes(res) == ["2 dry moves — deviating"]
    assert deviation_notes(EngineResult(style="x", seed=0)) == []


def test_planned_move_is_frozen_data():
    p = PlannedMove(role="oppose", target="H1", note="…")
    with pytest.raises(AttributeError):
        p.role = "weave"
