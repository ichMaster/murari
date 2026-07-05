"""murari — the agent output contract (v2) and fence/preamble-tolerant JSON extraction.

The run's last message is the JSON contract. In practice the model wraps it in a ```json
fence and sometimes prepends prose (v0.0 findings), so `extract_contract` locates the JSON
block wherever it is. `validate_contract` enforces the v2 schema and the source gate.
"""

from __future__ import annotations

import json
import re

ROLES = frozenset({"generate", "evaluate", "deepen", "oppose", "mutate", "weave"})
GENERATIVE_ROLES = frozenset({"generate", "mutate"})  # produce open candidates, never verdicts
MUTATION_TYPES = frozenset({"scale", "invert", "transfer", "combine", "analogy"})
STATUSES = frozenset({"open", "confirmed", "refuted", "partial"})
VERDICTS = frozenset({"confirmed", "refuted", "partial"})  # a verdict needs a source
BORN_FROM = frozenset({"search", "prior", "mutation", "user"})

TOP_KEYS = frozenset(
    {
        "role",
        "target_idea",
        "mutation_type",
        "hypotheses",
        "fresh_ideas",
        "next_probes",
        "next_role",
        "document_delta",
        "dry_run",
    }
)

_HID = re.compile(r"^H\d+$")
_FENCE = re.compile(r"```(?:[a-zA-Z0-9]*)\s*\n(.*?)\n```", re.S)


class ContractError(ValueError):
    """Raised when a run's output does not satisfy the v2 contract."""


def extract_contract(result_text: str) -> dict:
    """Parse the agent's final message into the contract dict. The model may emit the JSON
    bare, wrapped in a ```json fence, and/or after a prose preamble — locate the JSON block
    wherever it is rather than assuming the whole message is JSON. Raises on non-JSON."""
    s = result_text.strip()
    m = _FENCE.search(s)
    if m:
        return json.loads(m.group(1))
    a, b = s.find("{"), s.rfind("}")
    if a != -1 and b > a:
        return json.loads(s[a : b + 1])
    return json.loads(s)  # last resort — raises on junk


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ContractError(msg)


def _validate_hypothesis(h: object, role: str) -> None:
    _require(isinstance(h, dict), f"hypothesis must be an object: {h!r}")
    for k in ("id", "text", "status", "source", "parents"):
        _require(k in h, f"hypothesis missing key {k!r}: {h!r}")
    _require(
        isinstance(h["id"], str) and bool(_HID.match(h["id"])), f"bad hypothesis id: {h['id']!r}"
    )
    _require(
        isinstance(h["text"], str) and bool(h["text"].strip()), "hypothesis text must be non-empty"
    )
    status = h["status"]
    _require(status in STATUSES, f"bad status: {status!r}")
    src = h["source"]
    _require(src is None or (isinstance(src, str) and bool(src.strip())), f"bad source: {src!r}")
    # core value: no verdict without a source
    _require(
        not (status in VERDICTS and src is None),
        f"verdict {status!r} needs a source (id {h['id']})",
    )
    # source gate: generative roles produce only open candidates
    _require(
        not (role in GENERATIVE_ROLES and status != "open"),
        f"role {role!r} may only produce open candidates, got {status!r} (id {h['id']})",
    )
    parents = h["parents"]
    _require(isinstance(parents, list), "parents must be a list")
    for p in parents:
        _require(isinstance(p, str) and bool(_HID.match(p)), f"bad parent id: {p!r}")


def _validate_idea(idea: object) -> None:
    _require(isinstance(idea, dict), f"idea must be an object: {idea!r}")
    for k in ("text", "born_from", "basis"):
        _require(k in idea, f"idea missing key {k!r}: {idea!r}")
    _require(
        isinstance(idea["text"], str) and bool(idea["text"].strip()), "idea text must be non-empty"
    )
    _require(idea["born_from"] in BORN_FROM, f"bad born_from: {idea['born_from']!r}")
    _require(isinstance(idea["basis"], str), "idea basis must be a string")


def validate_contract(c: object) -> None:
    """Raise ContractError if `c` is not a valid v2 contract."""
    _require(isinstance(c, dict), "contract must be a JSON object")
    _require(TOP_KEYS <= set(c), f"missing keys: {sorted(TOP_KEYS - set(c))}")

    role = c["role"]
    _require(role in ROLES, f"bad role: {role!r}")

    target = c["target_idea"]
    _require(
        target is None or (isinstance(target, str) and bool(_HID.match(target))),
        f"bad target_idea: {target!r}",
    )

    mtype = c["mutation_type"]
    if role == "mutate":
        _require(mtype in MUTATION_TYPES, f"mutate needs a valid mutation_type, got {mtype!r}")
    else:
        _require(mtype is None, f"mutation_type must be null for role {role!r}, got {mtype!r}")

    _require(isinstance(c["hypotheses"], list), "hypotheses must be a list")
    for h in c["hypotheses"]:
        _validate_hypothesis(h, role)

    _require(isinstance(c["fresh_ideas"], list), "fresh_ideas must be a list")
    for idea in c["fresh_ideas"]:
        _validate_idea(idea)

    _require(
        isinstance(c["next_probes"], list) and all(isinstance(p, str) for p in c["next_probes"]),
        "next_probes must be a list of strings",
    )

    nr = c["next_role"]
    _require(nr is None or nr in ROLES, f"bad next_role: {nr!r}")

    dd = c["document_delta"]
    if role == "weave":
        _require(isinstance(dd, str) and bool(dd.strip()), "weave must report a document_delta")
    else:
        _require(dd is None, f"document_delta must be null for role {role!r}, got {dd!r}")

    _require(isinstance(c["dry_run"], bool), f"dry_run must be a bool, got {c['dry_run']!r}")
