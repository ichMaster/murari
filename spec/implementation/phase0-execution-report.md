# Phase p0 — Execution Report

**Date:** 2026-07-04
**Branch:** main
**Label:** p0::phase:0
**Target version:** none — v0.0 ships no release (first tag is 0.1.0 after v0.1)
**Executed by:** Claude Code

## Summary

| Status | Count |
|--------|-------|
| Completed | 5 |
| Failed | 0 |
| Skipped | 0 |
| Remaining | 0 |

**Phase v0.0 DoD holds.** The brainstormer loop was proven by a real by-hand run, and the
two seams (JSON output contract, workspace file formats) are pinned by tests that pass
offline against the captured fixtures. `python3 -m pytest tests/` → **12 passed**.

## Issues

| # | MUR ID | Title | Phase | Status | Commit | Files | Tests |
|---|--------|-------|-------|--------|--------|-------|-------|
| 1 | MUR-001 | Install the brainstormer agent | p0 | completed | eab46cb | 1 | n/a |
| 2 | MUR-002 | Hand-written test session workspace (TOPIC.md) | p0 | completed | b3d1a1c | 1 | n/a |
| 3 | MUR-003 | By-hand run: fire the loop and capture artifacts | p0 | completed | 0279f75 | 9 | by-hand run |
| 4 | MUR-004 | Contract test: pin the agent JSON output schema | p0 | completed | 67b3d8a | 1 | 7 passed |
| 5 | MUR-005 | Workspace-format test: pin LEDGER structure + dry-run counter | p0 | completed | b41295e | 1 | 5 passed |

## Detailed Results

### MUR-001: Install the brainstormer agent — completed (eab46cb)
- `.claude/agents/brainstormer.md` installed byte-identical to `spec/brainstormer.md`; frontmatter = closed quartet + `model: opus`.

### MUR-002: Hand-written test session workspace — completed (b3d1a1c)
- `tests/fixtures/session-2026-07-04-1400-teplovi-nasosy/TOPIC.md` (Ukrainian, 2 web-verifiable seeds); only TOPIC.md present.

### MUR-003: By-hand run — completed (0279f75)
- Real paid run on `claude-opus-4-8` ×2; artifacts under `tests/fixtures/captured-run/` (+ NOTES.md).
- **DoD:** valid contract; ledger accumulates 5→7 (confirmed 1→3, no closed re-checked); `born_from: search` ideas traceable; `DOCUMENT.md` coherent state.
- **Findings → spec/architecture.md:** (1) `--agents brainstormer` doesn't run as the agent with Task disabled → `--append-system-prompt` with the canon body; (2) JSON is ```json-fenced → parser strips it; (3) `web_search_requests` counter unreliable in Claude Code.

### MUR-004: Contract test — completed (67b3d8a)
- `tests/test_agent_output_contract.py` — schema + status enum pinned; fence stripped; malformed rejected. **7 passed.**

### MUR-005: Workspace-format test — completed (b41295e)
- `tests/test_workspace_format.py` — LEDGER structure + dry-run counter + SOURCES/IDEAS/DOCUMENT + cross-run accumulation. **5 passed.**

## Validation notes

- **Tests:** `pytest tests/` → 12 passed (offline, no paid calls).
- **ruff:** not installed on this machine — the lint check was skipped (to be wired with `pyproject.toml` in v0.1).
- **No paid APIs in CI:** the only paid call was MUR-003's sanctioned by-hand run; the tests run purely on captured fixtures.

## Next Steps

- **No release** — v0.0 ships none by design (first tag is `0.1.0` after v0.1).
- Proceed to **v0.1 (Orchestration)**: `/generate-issues 1` → `/upload-issues` → `/execute-issues p1::phase:1`. v0.1 wires `pyproject.toml` (ruff + pytest), the `AgentRunner` seam (encapsulating the verified `--append-system-prompt` invocation + fence-stripping parser), the session lifecycle, and budgets.
