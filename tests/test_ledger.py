"""MUR-008 — LEDGER v2: parsing, lineage helpers, and per-move dry-run. Mocks only."""

from __future__ import annotations

from pathlib import Path

import pytest

from murari.ledger import LedgerError, is_dry, is_productive, parse_ledger

FULL = (Path(__file__).parent / "fixtures" / "ledger-v2" / "full.md").read_text(encoding="utf-8")


def _led(hyp_lines: str = "", dry: int = 0, ranking: str = "", arguments: str = ""):
    """Build a Ledger from hypothesis lines (+ empty journal, optional ranking / arguments)."""
    rank = f"\n## Ранжування\n{ranking}\n" if ranking else ""
    args = f"\n## Аргументи\n{arguments}\n" if arguments else ""
    return parse_ledger(
        f"# LEDGER\n\n## Гіпотези\n{hyp_lines}\n\n## Прогони\n{rank}{args}\n"
        f"## Сухі прогони поспіль: {dry}\n"
    )


# --- scoring (## Ранжування) ---


def test_parse_scores():
    led = _led(
        "- [H1][open] ідея\n- [H2][open] інша\n",
        ranking="- H1 — доказ:2 ориг:4 попул:2 поясн:3 — джерела: ні\n"
        "- H2 — доказ:5 ориг:2 попул:4 поясн:4 — джерела: так\n",
    )
    assert {s.hid for s in led.scores} == {"H1", "H2"}
    s1 = led.score("H1")
    assert s1.axes == (2, 4, 2, 3) and s1.sourced is False
    assert led.score("H2").sourced is True


def test_scores_optional():
    assert _led("- [H1][open] ідея\n").scores == ()  # no Ранжування section is fine


def test_score_out_of_range_raises():
    with pytest.raises(LedgerError, match="1–5"):
        _led("- [H1][open] ідея\n", ranking="- H1 — доказ:9 ориг:4 попул:2 поясн:3 — джерела: ні\n")


def test_score_for_unknown_hypothesis_raises():
    with pytest.raises(LedgerError, match="unknown hypothesis"):
        _led("- [H1][open] ідея\n", ranking="- H7 — доказ:2 ориг:4 попул:2 поясн:3 — джерела: ні\n")


# --- arguments (## Аргументи) ---


def test_parse_arguments():
    led = _led(
        "- [H2][partial] wetware — джерело: https://e.com/x\n- [H3][open] інша\n",
        arguments=(
            "### H2\n"
            "- ЗА: два продукти з цифрами — джерело: https://e.com/za\n"
            "- ПРОТИ: нема памʼяті між сесіями — джерело: https://e.com/proti\n"
            "### H3\n"
            "- ПРОТИ: без джерела ще\n"
        ),
    )
    h2 = led.arguments_for("H2")
    assert [a.side for a in h2] == ["за", "проти"]
    assert h2[0].source == "https://e.com/za" and "продукти" in h2[0].text
    h3 = led.arguments_for("H3")
    assert len(h3) == 1 and h3[0].side == "проти" and h3[0].source is None


def test_arguments_optional():
    assert _led("- [H1][open] a\n").arguments == ()


def test_argument_for_unknown_hypothesis_raises():
    with pytest.raises(LedgerError, match="unknown hypothesis"):
        _led("- [H1][open] a\n", arguments="### H9\n- ЗА: x — джерело: https://e.com/1\n")


def test_argument_without_heading_raises():
    with pytest.raises(LedgerError, match="before any"):
        _led("- [H1][open] a\n", arguments="- ЗА: x — джерело: https://e.com/1\n")


def test_deepen_productive_via_arguments():
    before = _led("- [H1][open] a\n")
    after = _led(
        "- [H1][open] a\n",
        arguments="### H1\n- ЗА: x — джерело: https://e.com/1\n- ПРОТИ: y — джерело: https://e.com/2\n",
    )
    # deepen with no SOURCES delta is still productive if it wrote ≥2 arguments
    assert is_productive("deepen", before, after, sources_added=0) is True


def test_score_only_evaluate_is_productive():
    before = _led("- [H1][open] a\n- [H2][open] b\n")
    after = _led(
        "- [H1][open] a\n- [H2][open] b\n",
        ranking="- H1 — доказ:2 ориг:4 попул:2 поясн:3 — джерела: ні\n",
    )
    # explore's unsourced scoring adds no verdict, but a fresh score keeps it productive
    assert is_productive("evaluate", before, after) is True
    assert is_dry("evaluate", before, after) is False


# --- parsing ---


def test_parse_full_hypotheses():
    led = parse_ledger(FULL)
    assert {h.id for h in led.hypotheses} == {"H1", "H2", "H3", "H4", "H7", "H9"}
    h1 = led.by_id("H1")
    assert h1.status == "confirmed"
    assert h1.source == "https://example.com/a"
    assert h1.tested == 2
    h3 = led.by_id("H3")
    assert h3.status == "partial" and h3.note == "залежить від умов"
    h7 = led.by_id("H7")
    assert h7.parents == ("H3",) and h7.mutation == "invert" and h7.status == "open"
    assert led.by_id("H9").parents == ("H3", "H5")
    assert led.dry_streak == 0


def test_parse_full_journal():
    led = parse_ledger(FULL)
    assert len(led.runs) == 4
    assert led.runs[0].move == "generate" and led.runs[0].executor == "агент"
    assert led.runs[2].executor == "користувач"  # oppose(користувач)
    assert led.runs[3].move == "mutate" and led.runs[3].produced == "H7"


def test_next_id():
    assert parse_ledger(FULL).next_id() == "H10"
    assert _led().next_id() == "H1"  # empty ledger


def test_descendants():
    led = parse_ledger(FULL)
    kids = {h.id for h in led.descendants("H3")}
    assert kids == {"H7", "H9"}  # both name H3 as a parent


def test_survivors_and_strongest():
    led = parse_ledger(FULL)
    assert {h.id for h in led.survivors()} == {"H1", "H3"}  # confirmed + partial
    assert led.strongest().id == "H1"  # confirmed, випробувано 2
    assert led.strongest(led.survivors()).id == "H1"


def test_dash_in_hypothesis_text_preserved():
    led = _led("- [H1][open] ідея — з тире — всередині")
    assert led.by_id("H1").text == "ідея — з тире — всередині"


# --- malformed ---


def test_missing_dry_counter_raises():
    with pytest.raises(LedgerError):
        parse_ledger("# LEDGER\n\n## Гіпотези\n- [H1][open] x\n")


def test_bad_status_raises():
    with pytest.raises(LedgerError):
        _led("- [H1][maybe] x")


def test_malformed_hypothesis_raises():
    with pytest.raises(LedgerError):
        _led("- [H1] no status bracket")


def test_duplicate_id_raises():
    with pytest.raises(LedgerError):
        _led("- [H1][open] a\n- [H1][open] b")


def test_not_a_ledger_raises():
    with pytest.raises(LedgerError):
        parse_ledger("just some text\n")


# --- per-move productivity ---


def test_generate_productive():
    before = _led()
    after = _led("- [H1][open] a\n- [H2][open] b\n- [H3][open] c")
    assert is_productive("generate", before, after)
    two = _led("- [H1][open] a\n- [H2][open] b")
    assert is_dry("generate", before, two)


def test_evaluate_productive():
    before = _led("- [H1][open] твердження")
    after = _led("- [H1][confirmed] твердження — джерело: https://e.com/a")
    assert is_productive("evaluate", before, after)
    assert is_dry("evaluate", before, before)  # nothing verdicted


def test_deepen_uses_sources_added():
    z = _led()
    assert is_productive("deepen", z, z, sources_added=2)
    assert is_dry("deepen", z, z, sources_added=1)


def test_oppose_uses_sources_added():
    z = _led()
    assert is_productive("oppose", z, z, sources_added=1)
    assert is_dry("oppose", z, z, sources_added=0)


def test_mutate_productive():
    before = _led("- [H1][open] a")
    after = _led("- [H1][open] a\n- [H2][open] b — parents: H1 — mutation: invert")
    assert is_productive("mutate", before, after)
    assert is_dry("mutate", before, before)


def test_weave_uses_document_rebuilt():
    z = _led()
    assert is_productive("weave", z, z, document_rebuilt=True)
    assert is_dry("weave", z, z, document_rebuilt=False)


def test_unknown_move_raises():
    z = _led()
    with pytest.raises(LedgerError):
        is_productive("frobnicate", z, z)
