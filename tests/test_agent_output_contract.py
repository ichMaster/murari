"""Extractor — locate the JSON contract in a run's final message (bare / fenced / preamble).

The v2 schema itself is validated in test_contract.py. The captured v0.0 run (run-1.json)
is a v1-shape artifact kept only for the extractor regression — extraction is
version-independent, so it stays valid even though the schema moved to v2.
"""

from __future__ import annotations

import json
from pathlib import Path

from murari.contract import extract_contract

CAPTURED_RUN = Path(__file__).parent / "fixtures" / "captured-run" / "run-1.json"


def test_captured_run_extracts():
    envelope = json.loads(CAPTURED_RUN.read_text(encoding="utf-8"))
    c = extract_contract(envelope["result"])
    assert isinstance(c, dict) and "hypotheses" in c


def test_extract_bare():
    payload = {"hypotheses": [], "dry_run": False}
    assert extract_contract(json.dumps(payload)) == payload


def test_extract_strips_optional_fence():
    bare = json.dumps({"hypotheses": [], "dry_run": False})
    fenced = f"```json\n{bare}\n```"
    assert extract_contract(bare) == extract_contract(fenced)


def test_extract_handles_prose_preamble():
    # real runs sometimes prepend prose before the fenced JSON:
    # "Файли оновлено. … Повертаю JSON.\n\n```json\n{…}\n```"
    bare = json.dumps({"hypotheses": [], "dry_run": False})
    preamble = f"Файли оновлено. Повертаю JSON.\n\n```json\n{bare}\n```"
    assert extract_contract(preamble) == extract_contract(bare)
