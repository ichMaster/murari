# Phase p2 -- Execution Report

**Date:** 2026-07-15
**Branch:** main
**Label:** p2::phase:2
**Target version:** 0.2.0 (not bumped — release via `/release-version` on user confirmation)
**Executed by:** Claude Code

## Summary

| Status | Count |
|--------|-------|
| Completed | 6 |
| Failed | 0 |
| Skipped | 0 |
| Remaining | 0 |

Test suite grew **192 → 284** (all offline: mock Haiku + MockAgentRunner/FakeAgent — no paid
APIs anywhere). `ruff check` + `ruff format --check` clean at every commit.

## Issues

| # | MUR ID | Title | Phase | Status | Commit | Files | Tests |
|---|--------|-------|-------|--------|--------|-------|-------|
| 1 | MUR-012 | Haiku model seam + session auto-naming (Namer, local fallback) | p2 | completed | b23b9a4 | 10 | pass (210) |
| 2 | MUR-013 | Ведучий loop: facilitation prompt, single-tool boundary, dispatch | p2 | completed | 55fc170 | 8 | pass (223) |
| 3 | MUR-014 | Role detection + user moves: provenance, journal, H-id allocation | p2 | completed | 6455375 | 2 | pass (244) |
| 4 | MUR-015 | Move planner: complementarity, debate pairing, style selection | p2 | completed | 87e9019 (+2555b38) | 3 | pass (263) |
| 5 | MUR-016 | Seed extraction + result presentation (output is data) | p2 | completed | a685076 | 4 | pass (273) |
| 6 | MUR-017 | Chat REPL: commands, trigger policy, integration turn | p2 | completed | 11598d6 | 7 | pass (284) |

## Detailed Results

### MUR-012: Haiku model seam + session auto-naming

**Status:** completed · **Commit:** b23b9a4
**Files:** `murari/haiku.py` (new), `murari/config.py`, `murari/session.py`, `murari/cli.py`,
`conftest.py`, `tests/test_haiku.py` (new), `tests/test_config.py`, `pyproject.toml`,
`spec/architecture.md`, `docs/USAGE.md`

- `HaikuModel` protocol + `AnthropicHaikuModel` (Messages API; key/SDK resolved at call time;
  typed `HaikuError`) + `MockHaikuModel`; the optional `.[chat]` extra carries the SDK.
- `Namer` with a deterministic no-API `local_name` fallback; `new` writes `# <name>` atop
  TOPIC.md; `--name` bypasses; `list`/`open` render the name; `MURARI_CHAT_MODEL`
  (default `claude-haiku-4-5`).
- conftest autouse fixture strips `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` in every test.
- **Validation:** unit + contract (TOPIC.md heading format pinned); ruff pass.

### MUR-013: Ведучий loop — single-tool boundary + dispatch

**Status:** completed · **Commit:** 55fc170
**Files:** `murari/veduchyi.py` (new), `murari/engine.py`, `murari/runner.py`,
`murari/haiku.py`, `tests/test_veduchyi.py` (new), `tests/test_engine.py`,
`spec/architecture.md`, `spec/strategies.md`

- Exactly one tool — `run_brainstorm(seed, role, target_idea?, mutation_type?, style_step?,
  depth?)`; args validated as data → engine dispatch (single move via sequence override, or a
  styled run at depth) or a structured `Refusal`; budget refused before spending; run output
  returns as quoted `tool_result` JSON.
- Engine gains `sequence`/`mutation_override`/`seed_text`; kickoffs carry the Ведучий seed as
  quoted context. Tool signature updated in both specs (seam + contract test together).
- **Validation:** boundary contract test + dispatch/budget units; ruff pass.

### MUR-014: Role detection + user moves

**Status:** completed · **Commit:** 6455375
**Files:** `murari/participant.py` (new), `tests/test_participant.py` (new)

- `detect_role` (strategies reply table; every doubt/failure → `steering`) and
  `record_user_move`: sequential `[Hn][open] … born_from: user` candidates (+IDEAS),
  ЗА/ПРОТИ arguments for targeted deepen/oppose, journal-only Суддя/Ткач orders with the
  `(користувач)` executor; DOCUMENT.md never touched; no budget spent; source gate holds.
- **Validation:** per-role fixtures, format round-trips through the pinned LEDGER v2 reader,
  budget-free assertion; ruff pass.

### MUR-015: Move planner

**Status:** completed · **Commits:** 87e9019, 2555b38 (format fixup)
**Files:** `murari/planner.py` (new), `tests/test_planner.py` (new), `spec/roadmap.md`

- `plan_next_move`: complementarity by default (opposing user favors deepen/evaluate),
  adversarial pairing only in `debate` (sides swap; «переможця немає» framing), orders map
  directly, targets via the engine's strongest-survivor rules; `choose_style` (explicit wins,
  Haiku inference, `investigate` fallback); `deviation_notes` surfaces the engine's rule.
- Open question **style deviation rules** closed in the roadmap.
- **Validation:** complementarity matrix across styles × roles, pairing/swap, no-winner scan,
  inference fixtures; ruff pass.

### MUR-016: Seed extraction + result presentation

**Status:** completed · **Commit:** a685076
**Files:** `murari/presenter.py` (new), `tests/test_presenter.py` (new), `spec/roadmap.md`,
`spec/architecture.md`

- `extract_seed`/`deidentify` (emails, phones, addresses, introduced names never reach a
  kickoff); `present_result` (data only inside an escape-proof `<дані>…</дані>` quote, **no
  tools registered**, scripted tool call ignored, deterministic `local_summary` fallback —
  honest dry runs, sources named, never a winner).
- Open question **presentation format** closed: paraphrase-always; raw ledger only via /ledger.
- **Validation:** de-identification fixtures, result-as-data regression pin, fallback paths;
  ruff pass.

### MUR-017: Chat REPL

**Status:** completed · **Commit:** 11598d6
**Files:** `murari/chat.py` (new), `murari/cli.py`, `tests/test_chat.py` (new), `conftest.py`,
`docs/USAGE.md`, `spec/roadmap.md`, `spec/architecture.md`

- `murari chat [session|--new "<тема>"]`: reply → detect → record → plan → dispatch → present;
  `/style` `/go` `/ledger` `/quit`; failures degrade to chat messages; explicit
  reopen-to-continue.
- **Trigger policy decided and recorded** (register ✅ + open question closed): a classified
  reply auto-launches the planned move; steering only converses; `/go` always forces.
- **Validation:** command units + the phase DoD as integration scripts (facilitated turn,
  debate adversarial no-winner, budget-refusal, reopen-and-continue); ruff pass.

## Phase DoD check (roadmap §v0.2)

- [x] A substantive reply is classified into a role and the correct complementary move
      launches (adversarial in `debate`) — `test_classified_reply_autolaunches…`,
      `test_debate_turn_pairs_adversarially_no_winner`.
- [x] Results come back in human language — presenter + integration assertions.
- [x] Haiku can initiate nothing but `run_brainstorm` — boundary contract tests (loop tool
      list, foreign-tool refusal, presenter registers no tools).
- [x] A fresh `new` gets a Haiku title in TOPIC.md with a local fallback when keyless;
      `list`/`open` show it — MUR-012 tests.

## Contracts pinned this phase

The Haiku **single-tool boundary** (signature incl. `depth`), the **TOPIC.md heading** format,
the **result-as-data guard**, and the **user-move provenance** formats riding the existing
LEDGER v2 pins.

## Open questions closed this phase

Presentation format (MUR-016), trigger policy (MUR-017), style-deviation rules (MUR-015) —
each recorded in the specs in the same commit as its code.

## Next Steps

- None remaining for p2. Release `0.2.0` via `/release-version` when the user confirms.
- One optional real smoke run (by hand, MAX subscription + a real `ANTHROPIC_API_KEY` in
  `.env`) to validate the chat flow against reality; CI stays fully mocked.
