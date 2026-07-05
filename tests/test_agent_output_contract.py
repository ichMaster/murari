"""
MUR-004 — Contract test: pin the agent JSON output schema.

Seeded from the captured by-hand run (MUR-003) at tests/fixtures/captured-run/.
Pins the agent's output contract:

    {hypotheses[], fresh_ideas[], next_probes[], document_delta, dry_run}

with the hypothesis status enum open|confirmed|refuted|partial and source: url|null.
Stdlib only (json + re) so it runs under a bare `pytest tests/` — the full
pyproject/ruff/CI wiring lands in v0.1.

Finding recorded from the real run: the agent returns its JSON wrapped in a
```json ... ``` fence, despite the canon asking for none. The contract therefore is
"JSON, optionally fenced"; `extract_contract` strips an optional fence before parsing —
exactly what the v0.1 orchestrator's parser must do. See spec/architecture.md.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "captured-run"
CAPTURED_RUN = FIXTURES / "run-1.json"

STATUSES = {"open", "confirmed", "refuted", "partial"}
BORN_FROM = {"search", "prior"}
TOP_KEYS = {"hypotheses", "fresh_ideas", "next_probes", "document_delta", "dry_run"}


def extract_contract(result_text: str) -> dict:
    """Parse the agent's final message into the contract dict. The model may emit the
    JSON bare, wrapped in a ```json fence, and/or after a prose preamble (both seen in
    real runs) — so locate the JSON block wherever it is rather than assuming the whole
    message is JSON."""
    s = result_text.strip()
    # a fenced ```json ... ``` block anywhere (handles a prose preamble before it)
    m = re.search(r"```(?:[a-zA-Z0-9]*)\s*\n(.*?)\n```", s, re.S)
    if m:
        return json.loads(m.group(1))
    # otherwise the outermost {...} object
    a, b = s.find("{"), s.rfind("}")
    if a != -1 and b > a:
        return json.loads(s[a : b + 1])
    return json.loads(s)  # last resort — raises on junk


def validate_contract(c: dict) -> None:
    """Raise AssertionError if `c` is not a valid agent output contract."""
    assert isinstance(c, dict), "contract must be a JSON object"
    assert TOP_KEYS <= set(c), f"missing keys: {TOP_KEYS - set(c)}"
    assert isinstance(c["hypotheses"], list)
    assert isinstance(c["fresh_ideas"], list)
    assert isinstance(c["next_probes"], list)
    assert isinstance(c["document_delta"], str)
    assert isinstance(c["dry_run"], bool)
    for h in c["hypotheses"]:
        assert {"text", "status", "source"} <= set(h), f"hypothesis keys: {h}"
        assert isinstance(h["text"], str) and h["text"].strip()
        assert h["status"] in STATUSES, f"bad status: {h['status']}"
        assert h["source"] is None or isinstance(h["source"], str)
    for idea in c["fresh_ideas"]:
        assert {"text", "born_from", "basis"} <= set(idea), f"idea keys: {idea}"
        assert isinstance(idea["text"], str) and idea["text"].strip()
        assert idea["born_from"] in BORN_FROM, f"bad born_from: {idea['born_from']}"


@pytest.fixture(scope="module")
def captured_contract() -> dict:
    envelope = json.loads(CAPTURED_RUN.read_text(encoding="utf-8"))
    return extract_contract(envelope["result"])


def test_captured_run_has_result(captured_contract):
    # the envelope parsed and yielded a contract dict
    assert isinstance(captured_contract, dict)


def test_captured_run_validates(captured_contract):
    validate_contract(captured_contract)


def test_extract_strips_optional_fence():
    bare = json.dumps(
        {
            "hypotheses": [],
            "fresh_ideas": [],
            "next_probes": [],
            "document_delta": "x",
            "dry_run": False,
        }
    )
    fenced = f"```json\n{bare}\n```"
    assert extract_contract(bare) == extract_contract(fenced)


def test_extract_handles_prose_preamble():
    # real runs sometimes prepend prose before the fenced JSON:
    # "Файли оновлено. … Повертаю JSON.\n\n```json\n{…}\n```"
    bare = json.dumps(
        {
            "hypotheses": [],
            "fresh_ideas": [],
            "next_probes": [],
            "document_delta": "x",
            "dry_run": False,
        }
    )
    preamble = f"Файли оновлено. Повертаю JSON.\n\n```json\n{bare}\n```"
    assert extract_contract(preamble) == extract_contract(bare)


def test_status_enum_enforced():
    bad = {
        "hypotheses": [{"text": "t", "status": "maybe", "source": None}],
        "fresh_ideas": [],
        "next_probes": [],
        "document_delta": "x",
        "dry_run": False,
    }
    with pytest.raises(AssertionError):
        validate_contract(bad)


def test_missing_key_fails():
    bad = {
        "hypotheses": [],
        "fresh_ideas": [],
        "next_probes": [],
        "document_delta": "x",
    }
    with pytest.raises(AssertionError):
        validate_contract(bad)


def test_dry_run_must_be_bool():
    bad = {
        "hypotheses": [],
        "fresh_ideas": [],
        "next_probes": [],
        "document_delta": "x",
        "dry_run": "false",
    }
    with pytest.raises(AssertionError):
        validate_contract(bad)


def test_source_url_or_null():
    ok = {
        "hypotheses": [
            {"text": "a", "status": "confirmed", "source": "https://example.com"},
            {"text": "b", "status": "open", "source": None},
        ],
        "fresh_ideas": [],
        "next_probes": [],
        "document_delta": "x",
        "dry_run": False,
    }
    validate_contract(ok)  # must not raise
