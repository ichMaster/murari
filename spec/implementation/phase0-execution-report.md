# Phase p0 — Execution Report

**Date:** 2026-07-04
**Branch:** main
**Label:** p0::phase:0
**Target version:** none — v0.0 ships no release (first tag is 0.1.0 after v0.1)
**Executed by:** Claude Code

## Summary

| Status | Count |
|--------|-------|
| Completed | 2 |
| Failed | 0 |
| Skipped | 0 |
| Remaining | 3 |

Automated execution stopped at MUR-003 **by design**: it is the deliberate real,
paid, **by-hand** run (live model + live web, observed by a human for DoD-level
quality). MUR-004 and MUR-005 are seeded from MUR-003's captured artifacts, so they
are blocked until it completes.

## Issues

| # | MUR ID | Title | Phase | Status | Commit | Files | Tests |
|---|--------|-------|-------|--------|--------|-------|-------|
| 1 | MUR-001 | Install the brainstormer agent | p0 | completed | eab46cb | 1 | n/a (file install) |
| 2 | MUR-002 | Hand-written test session workspace (TOPIC.md) | p0 | completed | b3d1a1c | 1 | n/a (fixture) |
| 3 | MUR-003 | By-hand run: fire the loop and capture artifacts | p0 | **handed to user** | — | — | by-hand run |
| 4 | MUR-004 | Contract test: pin the agent JSON output schema | p0 | blocked (needs #3) | — | — | — |
| 5 | MUR-005 | Workspace-format test: pin LEDGER structure + dry-run counter | p0 | blocked (needs #3) | — | — | — |

## Detailed Results

### MUR-001: Install the brainstormer agent

**Status:** completed
**Commit:** eab46cb (auto-closed #1 via "Closes #1")
**Files changed:**
- `.claude/agents/brainstormer.md` (added — byte-identical to `spec/brainstormer.md`)

**Validation:**
- [x] File matches `spec/brainstormer.md` (diff empty): pass
- [x] Frontmatter = `tools: WebSearch, WebFetch, Read, Write`, `model: opus`; no Bash/Task: pass
- [x] Well-formed YAML frontmatter at the canonical path: pass
- [n/a] Live `claude -p` resolve: exercised by MUR-003 (no paid call spent here)
- [x] Acceptance criteria: all pass

---

### MUR-002: Hand-written test session workspace (TOPIC.md)

**Status:** completed
**Commit:** b3d1a1c (auto-closed #2 via "Closes #2")
**Files changed:**
- `tests/fixtures/session-2026-07-04-1400-teplovi-nasosy/TOPIC.md` (added)

**Validation:**
- [x] TOPIC.md present, Ukrainian, verifiable topic + seeds: pass
- [x] Only TOPIC.md in the dir (agent creates the rest on first run): pass
- [x] Seeds carry a factual core the web can confirm/refute: pass
- [x] Acceptance criteria: all pass

---

### MUR-003: By-hand run — fire the loop and capture artifacts

**Status:** handed to user (the deliberate real paid by-hand run)
**Why not automated:** needs a live `claude -p` against the live web, run ≥2 times,
with a human judging the DoD (ideas traceable to findings; document reads as coherent
prose). This is the roadmap's one sanctioned paid run — see roadmap §v0.0.

**What the user does:**
1. Run the brainstormer over the MUR-002 workspace ≥2 times, saving each run's JSON.
2. Confirm the DoD: valid JSON; `LEDGER.md` accumulates (closed hypotheses not re-checked);
   ≥1 idea `born_from: search` traceable to a finding; `DOCUMENT.md` rebuilt, not a log.
3. Commit the captured artifacts (one run's JSON + resulting LEDGER/SOURCES/IDEAS/DOCUMENT)
   as fixtures, and record the exact working invocation. Then close #3.

## Next Steps

- **MUR-003 (#3)** — user runs the by-hand session and commits the captured fixtures.
- **MUR-004 (#4)** — once #3's JSON fixture exists: write the JSON-schema contract test.
- **MUR-005 (#5)** — once #3's workspace fixtures exist: write the LEDGER-format test.
- After all three: v0.0 DoD holds → proceed to v0.1 (orchestration). **v0.0 ships no release.**
