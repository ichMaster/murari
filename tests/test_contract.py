"""MUR-007 — contract v2 schema: per-role fixtures validate; malformed variants rejected.

Each `_load` reads a fresh copy from disk, so per-test mutations never leak.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from murari.contract import ROLES, ContractError, validate_contract

FIX = Path(__file__).parent / "fixtures" / "contract-v2"


def _load(role: str) -> dict:
    return json.loads((FIX / f"{role}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("role", sorted(ROLES))
def test_valid_per_role(role):
    validate_contract(_load(role))  # must not raise


def test_bad_role():
    c = _load("evaluate")
    c["role"] = "planner"
    with pytest.raises(ContractError):
        validate_contract(c)


def test_unknown_mutation_type():
    c = _load("mutate")
    c["mutation_type"] = "teleport"
    with pytest.raises(ContractError):
        validate_contract(c)


def test_mutation_type_on_non_mutate():
    c = _load("evaluate")
    c["mutation_type"] = "scale"
    with pytest.raises(ContractError):
        validate_contract(c)


def test_missing_hypothesis_id():
    c = _load("evaluate")
    del c["hypotheses"][0]["id"]
    with pytest.raises(ContractError):
        validate_contract(c)


def test_bad_hypothesis_id():
    c = _load("evaluate")
    c["hypotheses"][0]["id"] = "idea-1"
    with pytest.raises(ContractError):
        validate_contract(c)


def test_verdict_without_source():
    c = _load("evaluate")
    c["hypotheses"][0]["source"] = None  # confirmed without a source
    with pytest.raises(ContractError):
        validate_contract(c)


def test_generative_role_cannot_confirm():
    c = _load("generate")
    c["hypotheses"][0]["status"] = "confirmed"
    c["hypotheses"][0]["source"] = (
        "https://example.com/x"  # even with a source, generate can't verdict
    )
    with pytest.raises(ContractError):
        validate_contract(c)


def test_document_delta_only_weave():
    c = _load("generate")
    c["document_delta"] = "sneaky doc write"
    with pytest.raises(ContractError):
        validate_contract(c)


def test_weave_needs_document_delta():
    c = _load("weave")
    c["document_delta"] = None
    with pytest.raises(ContractError):
        validate_contract(c)


def test_dry_run_must_be_bool():
    c = _load("weave")
    c["dry_run"] = "false"
    with pytest.raises(ContractError):
        validate_contract(c)


def test_bad_parent_id():
    c = _load("mutate")
    c["hypotheses"][0]["parents"] = ["X9"]
    with pytest.raises(ContractError):
        validate_contract(c)


def test_bad_target_idea():
    c = _load("deepen")
    c["target_idea"] = "the first one"
    with pytest.raises(ContractError):
        validate_contract(c)


@pytest.mark.parametrize("basis", [None, "grew from finding X", ""])
def test_idea_basis_is_optional_and_nullable(basis):
    # basis is a soft note (meaningful only for search-born ideas); null / missing is fine
    c = _load("generate")
    c["fresh_ideas"][0]["basis"] = basis
    validate_contract(c)  # must not raise
    del c["fresh_ideas"][0]["basis"]
    validate_contract(c)  # missing entirely is also fine


def test_idea_basis_wrong_type_rejected():
    c = _load("generate")
    c["fresh_ideas"][0]["basis"] = 42  # a number is not a valid basis
    with pytest.raises(ContractError):
        validate_contract(c)


def test_idea_still_requires_born_from():
    c = _load("generate")
    del c["fresh_ideas"][0]["born_from"]
    with pytest.raises(ContractError):
        validate_contract(c)
