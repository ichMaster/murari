# Phase p3 -- Execution Report

**Date:** 2026-07-16
**Branch:** main
**Label:** p3::phase:3
**Target version:** 0.3.0 (not bumped — release via `/release-version` on user confirmation)
**Executed by:** Claude Code

## Summary

| Status | Count |
|--------|-------|
| Completed | 5 |
| Failed | 0 |
| Skipped | 0 |
| Remaining | 0 |

Test suite grew **302 → 318**, all headless (Textual pilot + mock Haiku + MockAgentRunner/
FakeAgent — no paid APIs). `ruff check` + `ruff format --check` clean at every commit.

## Issues

| # | MUR ID | Title | Phase | Status | Commit | Files | Tests |
|---|--------|-------|-------|--------|--------|-------|-------|
| 1 | MUR-018 | TUI scaffold: textual extra, app shell, layout + status bar | p3 | completed | 6dad2a3 | 6 | pass (307) |
| 2 | MUR-019 | Panels: lineage tree + journal, read-only markdown document | p3 | completed | adb3751 | 2 | pass (310) |
| 3 | MUR-020 | Async runs: worker seam, non-blocking chat, status transitions | p3 | completed | f128371 | 3 | pass (312) |
| 4 | MUR-021 | Commands: /b, /open + delegation to ChatSession | p3 | completed | 1fee7f8 | 3 | pass (317) |
| 5 | MUR-022 | Phase integration: the DoD as a driven-TUI script + docs | p3 | completed | 70d21af | 4 | pass (318) |

## Detailed Results

### MUR-018: TUI scaffold

**Status:** completed · **Commit:** 6dad2a3
**Files:** `murari/tui.py` (new), `murari/cli.py`, `tests/test_tui.py` (new), `pyproject.toml`,
`spec/roadmap.md`, `spec/architecture.md`

- `MurariApp` with the decided layout — chat left; right column: ledger top, document below;
  `StatusBar` docked at the bottom (style/depth · хід · залишилось ходів · idle/копає);
  `runs_remaining` computed from journaled agent moves.
- `murari tui` shares `_resolve_chat_session` with `chat`; textual imported lazily — the
  missing `[tui]` extra degrades to an install hint. `pytest-asyncio` (auto) + textual join
  the dev extra.
- Decisions closed: **panel layout** (register ✅, open question removed, architecture updated).

### MUR-019: Panels

**Status:** completed · **Commit:** adb3751
**Files:** `murari/tui.py`, `tests/test_tui.py`

- Ledger panel: lineage `Tree` (a combine child under BOTH parents; plain-text labels so
  `[open]` isn't eaten as Rich markup) with status, ★ scores (дж/чорн), «випробувано»,
  за/проти counts; journal + dry counter below.
- Document panel: markdown with an explicit empty state and **no input-capable widget** —
  the ownership invariant pinned at the UI level; malformed ledger renders an error line.

### MUR-020: Async runs

**Status:** completed · **Commit:** f128371
**Files:** `murari/tui.py`, `tests/test_tui.py`, `spec/roadmap.md`

- Every turn in a `@work(thread=True, exit_on_error=False)` worker; the ⚙ announce + engine
  progress stream in live via `call_from_thread`, driving the dig label + elapsed seconds;
  completion refreshes panels and renders the separated reply; failures land as chat lines.
- Policy decided and pinned: a second submit while digging is **politely refused** (nothing
  queues silently). Register row **async run + non-blocking chat** → accepted.

### MUR-021: Commands

**Status:** completed · **Commit:** 1fee7f8
**Files:** `murari/tui.py`, `murari/cli.py`, `tests/test_tui.py`

- `/b <тема>` (fresh named session, blank state — no implicit memory) and `/open <шлях>`
  (explicit continuation; bad path degrades gracefully) switch the whole app; both behind
  the busy guard. `/style`, `/go`, `/help`, `/ledger`, unknown → ChatSession delegation;
  `/quit` exits with the dir intact. Startup help names /b and /open.

### MUR-022: Integration + docs

**Status:** completed · **Commit:** 70d21af
**Files:** `tests/test_tui.py`, `README.md`, `docs/USAGE.md`, `CLAUDE.md`

- `test_v03_dod_script` drives the full roadmap §v0.3 DoD headless under the pilot.
- Docs: README TUI section, USAGE `murari tui` row, CLAUDE.md interface section flipped
  from "planned" to shipped (v0.2 REPL + v0.3 TUI, router semantics).

## Phase DoD check (roadmap §v0.3)

- [x] A `/b` session shows the chat, the ledger filling, the document rebuilding after weave
      — `test_v03_dod_script`.
- [x] Chat stays usable during runs — `test_chat_stays_responsive_during_run` (gated runner).
- [x] `/style` switches scenarios; `/open` continues a prior document; `/quit` leaves the
      session dir on disk — command tests + the DoD script.

## Contracts pinned this phase

No stable seams changed. UI-level re-assertions: the document surface is read-only (no
input-capable widget) and every run still passes the v0.2 single-tool boundary. Decisions
closed: panel layout (MUR-018), async run + non-blocking chat (MUR-020).

## Next Steps

- None remaining for p3. Release `0.3.0` via `/release-version` when the user confirms.
- v0.4 (sandbox hardening) is the next roadmap phase.
