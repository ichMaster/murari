# Phase p1 — Execution Report

**Date:** 2026-07-05
**Branch:** main
**Label:** p1::phase:1
**Target version:** 0.1.0 (not yet released — awaiting `/release-version`)
**Executed by:** Claude Code

## Summary

| Status | Count |
|--------|-------|
| Completed | 6 |
| Failed | 0 |
| Skipped | 0 |
| Remaining | 0 |

All six v0.1 issues (MUR-006 … MUR-011) implemented, validated, committed, pushed, and closed
in dependency order. Test suite ends at **113 passing**; `ruff check` and `ruff format --check`
clean. No paid APIs anywhere in CI — the agent (`claude -p`) is behind the `AgentRunner` seam and
driven by `MockAgentRunner` + a scripted `FakeAgent`.

## Issues

| # | MUR ID | Title | Phase | Status | Commit | Files | Tests |
|---|--------|-------|-------|--------|--------|-------|-------|
| 1 | MUR-006 | Project scaffolding: pyproject, package layout, config | p1 | completed | 2861027 | 13 | pass |
| 2 | MUR-007 | Canon v2 install + contract v2 re-pin | p1 | completed | c1ba233 | 10 | pass |
| 3 | MUR-008 | LEDGER v2: parser, lineage, journal, per-move dry-run | p1 | completed | d3ca585 | 4 | pass |
| 4 | MUR-009 | AgentRunner seam: verified invocation, per-role tools, mock | p1 | completed | 8fec814 | 2 | pass |
| 5 | MUR-010 | Session lifecycle: create, open-and-continue, graceful failure | p1 | completed | 5ac54a4 | 2 | pass |
| 6 | MUR-011 | Style engine + CLI: sequences, randomness, budgets, ownership | p1 | completed | 9485441 | 6 | pass |

## Detailed Results

### MUR-006: Project scaffolding: pyproject, package layout, config

**Status:** completed · **Commit:** 2861027

- `pyproject.toml` (ruff `E,W,F,I,UP,B`, line-length 100, dynamic version from `VERSION`,
  `[project.scripts] murari = murari.cli:main`), the `murari/` package skeleton, and
  `murari/config.py` (frozen `Config`, `load_config`, dependency-free `.env` loader; defaults
  RUNS=6 / MAX_TURNS=15 / MODEL=`claude-opus-4-8`, `MURARI_HOME` → gitignored `.murari/`).

**Validation:** unit tests (config), ruff, py_compile — all pass.

---

### MUR-007: Canon v2 install + contract v2 re-pin

**Status:** completed · **Commit:** c1ba233

- Installed the role-parameterized canon at `.claude/agents/brainstormer.md` and pinned the v2
  JSON contract in `murari/contract.py` (`ROLES`, `GENERATIVE_ROLES`, `MUTATION_TYPES`,
  `STATUSES`, `VERDICTS`, `extract_contract`, `validate_contract`). Retired the v1 contract tests
  and added the v2 extractor/schema tests + six per-role fixtures.

**Validation:** contract tests, extractor tests, ruff — all pass.

---

### MUR-008: LEDGER v2: parser, lineage, journal, per-move dry-run

**Status:** completed · **Commit:** d3ca585

- `murari/ledger.py`: parses LEDGER v2 (H-ids, statuses, source, «випробувано», `parents`,
  `mutation`, the run journal, and the «Сухі прогони поспіль» counter), with lineage helpers
  (`descendants`, `survivors`, `strongest`) and the per-move productivity check
  `is_productive`/`is_dry` (thresholds from strategies.md). Malformed lines raise `LedgerError`.

**Validation:** ledger parse/lineage/dry-run tests, ruff — all pass.

---

### MUR-009: AgentRunner seam: verified invocation, per-role tools, mock

**Status:** completed · **Commit:** 8fec814

- `murari/runner.py`: `ClaudeCliRunner` builds the verified `claude -p` command (canon body via
  `--append-system-prompt`, `--model` from config, per-role `--allowedTools` narrowing with the
  analogy exception, `--disallowedTools Bash,Task`, `--output-format json`, `cwd` = session dir)
  and parses the envelope through `murari.contract`. `MockAgentRunner` returns canned per-role
  contracts, records calls, and can mutate the workspace via `on_run` — reused by MUR-011.

**Validation:** tool-matrix / command-builder / envelope-parser / mock tests, ruff — all pass.
No real `claude` invocation.

---

### MUR-010: Session lifecycle: create, open-and-continue, graceful failure

**Status:** completed · **Commit:** 5ac54a4

- `murari/session.py`: create a fresh `MURARI_HOME/brainstorm-sessions/session-<stamp>[-slug]/`
  (input/output split, collision-safe, ASCII slug), `open_session` to continue an existing one,
  `list_sessions` (most recent first), and `snapshot_state`/`restore_state` so a failed run leaves
  the output state files byte-identical. Timestamp is injectable for deterministic tests.

**Validation:** create/open/list/failure-hygiene tests, ruff — all pass.

---

### MUR-011: Style engine + CLI: sequences, randomness, budgets, ownership

**Status:** completed · **Commit:** 9485441

- `murari/engine.py`: run a style (explore/debate/riff/investigate(default)/evolve/premortem) as
  its accepted move sequence, re-reading LEDGER between moves. Seeded orchestrator randomness
  (mutation types + combine partners; seed recorded in `output/artifacts/engine.log`). Target
  selection picks the strongest relevant hypothesis (survivors first); the combine partner is the
  strongest other. Two dry moves in a row deviate to the agent's `next_role` or a fallback
  (mutate survivors, else generate), logged with justification. Budgets stop at `MURARI_RUNS`
  (`--moves` caps below); per-move profiles (generate/mutate/weave cheap, evaluate/oppose medium,
  deepen expensive) match architecture.md. DOCUMENT ownership guard: only `weave` may write it.
- `murari/cli.py`: headless `new`/`open`/`run`/`list` over an injectable AgentRunner, wrapped in
  snapshot/restore. `murari/runner.py`: `AgentRunner` Protocol + `RunRequest.partner_idea` and the
  combine branch in `build_prompt`. `conftest.py`: a scripted `FakeAgent` for full mocked runs.

**Validation:**
- [x] Unit + contract tests (pytest): **113 passed** (32 new across test_engine.py + test_cli.py)
- [x] Lint (ruff check): pass
- [x] Format (ruff format --check): pass
- [x] CLI smoke (`python -m murari.cli --help`): pass
- [x] Acceptance criteria: all pass

## v0.1 Definition of Done — status

| DoD item (roadmap §v0.1) | Status |
|---|---|
| Styled session driven from the CLI (`new`/`open`/`run`, default `investigate`) | ✅ |
| Ledger carries ids / lineage (`parents`, `mutation`) / run journal | ✅ |
| Budgets honored (`MURARI_RUNS`, `MURARI_MAX_TURNS`), per-move profiles logged | ✅ |
| Only `weave` writes DOCUMENT.md (ownership guard) | ✅ |
| Graceful degradation (2 dry → deviation with justification) | ✅ |
| Open-and-continue grows the same workspace | ✅ |
| All six roles born as canon modules, driven by the style engine | ✅ |
| No paid APIs in CI (agent/Haiku/web-search mocked) | ✅ |

## Next Steps

- **No issues remain** in phase v0.1. All six are closed on GitHub.
- **Release is not automatic.** When ready, cut the phase release with
  `/release-version 0.1.0` (first tagged release — v0.0 shipped none).
- Next roadmap phase is **v0.2 — Chat layer (Haiku)**: `/generate-issues v0.2`, then
  `/upload-issues`, then `/execute-issues p2::phase:2`.

## Companion documents

- [roadmap.md](../roadmap.md) — version goals, per-phase Goal/Tasks/DoD/Tests (§v0.1).
- [architecture.md](../architecture.md) — the two-head architecture, styles, budgets, sandbox invariants.
- [strategies.md](../strategies.md) — roles, mutation types, styles, contract v2 (accepted 2026-07-05).
- [phase1-issues.md](phase1-issues.md) — the issue breakdown.
- [phase1-github-report.md](phase1-github-report.md) — MUR-xxx → GitHub # mapping.
