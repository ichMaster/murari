"""
MUR-005 — Workspace-format test: pin LEDGER.md structure + dry-run counter.

Seeded from the captured by-hand run (MUR-003). Pins the workspace file formats the
canon defines (spec/brainstormer.md) and encodes the DoD-level checks:
  - LEDGER.md structure: `# LEDGER`, `## Гіпотези` with `[status]` entries, verdicts
    carry a source, and the `## Сухі прогони поспіль: N` counter.
  - accumulation across the >=2 captured runs: verdicts are sticky (a closed hypothesis
    is not re-opened; the ledger does not shrink).
  - IDEAS.md carries a `born_from: search` idea with a `basis`.
  - DOCUMENT.md is rebuilt state, not a per-run log.

Fixtures:
  fixtures/captured-run/LEDGER.md            (final, after run-2)
  fixtures/captured-run/{SOURCES,IDEAS,DOCUMENT}.md
  fixtures/captured-run/after-run-1/LEDGER.md  (snapshot after run-1, for accumulation)

Stdlib only; runs under a bare `pytest tests/`.
"""

from __future__ import annotations

import re
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "captured-run"
STATUSES = {"open", "confirmed", "refuted", "partial"}
CLOSED = {"confirmed", "refuted"}

_HYP = re.compile(r"^- \[(\w+)\]\s+(.+)$", re.M)
_DRY = re.compile(r"^##\s*Сухі прогони поспіль:\s*(\d+)\s*$", re.M)


def parse_ledger(text: str):
    """Return (hypotheses, dry_run_count). hypotheses = list of (status, body)."""
    assert text.lstrip().startswith("# LEDGER"), "LEDGER.md must start with '# LEDGER'"
    assert "## Гіпотези" in text, "LEDGER.md must have a '## Гіпотези' section"
    hyps = _HYP.findall(text)
    m = _DRY.search(text)
    assert m, "LEDGER.md must carry the 'Сухі прогони поспіль: N' counter"
    return hyps, int(m.group(1))


def test_ledger_structure_and_counter():
    hyps, dry = parse_ledger((FIXTURES / "LEDGER.md").read_text(encoding="utf-8"))
    assert hyps, "no hypotheses parsed from LEDGER.md"
    assert dry >= 0
    for status, body in hyps:
        assert status in STATUSES, f"unknown status [{status}]"
        if status in CLOSED or status == "partial":
            assert "джерело:" in body and "http" in body, (
                f"a {status} verdict must carry a source URL: {body[:60]}"
            )


def test_sources_are_url_lines():
    text = (FIXTURES / "SOURCES.md").read_text(encoding="utf-8")
    assert text.lstrip().startswith("# SOURCES")
    urls = [ln for ln in text.splitlines() if ln.strip().startswith("- http")]
    assert urls, "SOURCES.md must list at least one 'url — note' line"


def test_ideas_has_born_from_search_with_basis():
    text = (FIXTURES / "IDEAS.md").read_text(encoding="utf-8")
    search_lines = [ln for ln in text.splitlines() if "born_from: search" in ln]
    assert search_lines, "IDEAS.md must contain >=1 'born_from: search' idea"
    assert any("basis:" in ln for ln in search_lines), (
        "a born_from: search idea must cite the finding via 'basis:'"
    )


def test_document_is_state_not_log():
    text = (FIXTURES / "DOCUMENT.md").read_text(encoding="utf-8")
    assert text.lstrip().startswith("# "), "DOCUMENT.md must have a title (coherent state)"
    # a rebuilt document, not an appended per-run log
    assert not re.search(r"Прогін\s*\d", text), "DOCUMENT.md must not read as a run log"
    # coherent, structured synthesis (state), not a stub
    assert len(re.findall(r"^##\s", text, re.M)) >= 3, (
        "DOCUMENT.md should be a structured synthesis"
    )
    assert len(text) > 800, "DOCUMENT.md should be a substantive document"
    # NOTE: source *URLs* live in SOURCES.md / LEDGER.md (asserted by their own tests);
    # DOCUMENT.md is readable prose carrying sourced figures, not inline URLs.


def test_ledger_accumulates_across_runs():
    """Verdicts are sticky: run-2 keeps the closed verdicts from run-1 and does not
    shrink the ledger or re-open a closed hypothesis."""
    h1, _ = parse_ledger((FIXTURES / "after-run-1" / "LEDGER.md").read_text(encoding="utf-8"))
    h2, _ = parse_ledger((FIXTURES / "LEDGER.md").read_text(encoding="utf-8"))
    closed1 = sum(1 for s, _ in h1 if s in CLOSED)
    closed2 = sum(1 for s, _ in h2 if s in CLOSED)
    assert len(h2) >= len(h1), "the ledger shrank across runs (state not accumulated)"
    assert closed2 >= closed1, "a closed verdict was lost across runs (re-checked)"
