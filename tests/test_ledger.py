"""MUR-008 — LEDGER v2: parsing, lineage helpers, and per-move dry-run. Mocks only."""

from __future__ import annotations

from pathlib import Path

import pytest

from murari.ledger import LedgerError, is_dry, is_productive, parse_ledger

FULL = (Path(__file__).parent / "fixtures" / "ledger-v2" / "full.md").read_text(encoding="utf-8")


def _led(hyp_lines: str = "", dry: int = 0):
    """Build a Ledger from just the hypothesis lines (+ empty journal)."""
    return parse_ledger(
        f"# LEDGER\n\n## Гіпотези\n{hyp_lines}\n\n## Прогони\n\n## Сухі прогони поспіль: {dry}\n"
    )


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
