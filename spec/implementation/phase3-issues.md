# Phase v0.3 — GitHub Issues

Issues for phase **v0.3 — TUI (Textual)** (version **v0 — the prototype**), derived from the
per-phase Goal / Tasks / DoD / Tests in [roadmap.md](../roadmap.md) (§v0.3) and the contracts
in [architecture.md](../architecture.md). This file is scoped to a single phase; IDs continue
from the previous phase (MUR-017 → **MUR-018…MUR-022**).

v0.3 gives the v0.2 chat pipeline a face: a Textual **three-panel interface** — chat, ledger
(statuses, lineage, journal), and the read-only working document — with a status bar and
**async runs** so the chat stays usable while the agent digs. No new roles, no new seams: the
TUI *reads* the workspace and drives the existing `ChatSession`; every run still passes the
v0.2 single-tool boundary. Two open items get closed here: the panel **layout** and the
**async run + non-blocking chat** tentative decision.

## Issues Summary Table

| # | ID | Title | Size | Area | Phase | Dependencies |
|---|----|-------|------|------|-------|--------------|
| 1 | MUR-018 | TUI scaffold: textual extra, app shell, layout + status bar | M | tui | p3 | -- |
| 2 | MUR-019 | Panels: ledger (lineage/journal) + read-only document, re-read on completion | M | tui | p3 | MUR-018 |
| 3 | MUR-020 | Async runs: worker seam, non-blocking chat, status transitions | L | tui | p3 | MUR-018, MUR-019 |
| 4 | MUR-021 | Commands: /b, /open, /style, /go, /help, /ledger, /quit | M | tui | p3 | MUR-018 |
| 5 | MUR-022 | Phase integration: the DoD as a driven-TUI script + docs | S | tui | p3 | MUR-019, MUR-020, MUR-021 |

**Size legend:** S = 1–2 days, M = 3–5 days, L = 5–8 days
**Area:** agent · chat · tui · orchestrator · sandbox · tests · spec

---

## Dependency Tree

```
MUR-018 (scaffold: app shell + layout + status bar)
  |
  +-- MUR-019 (panels + re-read on completion) --+-- MUR-020 (async runs, non-blocking chat) --+
  |                                                                                            |
  +-- MUR-021 (commands) -----------------------------------------------------------------------+
                                                                                                |
                                                                MUR-022 (integration + docs)
                                                                  => v0.3 DoD (a live /b session)
```

**Parallelization hints:** MUR-018 first (gate — every issue lands widgets inside its shell).
Then MUR-019 and MUR-021 in parallel; MUR-020 builds on the panels. MUR-022 integrates the DoD.

---

## v0.3 — TUI (Textual)

### MUR-018 — TUI scaffold: textual extra, app shell, layout + status bar

**Description:**
Stand up the Textual application: the optional `[tui]` dependency, the `murari tui` entry
point, the decided panel layout, and the status bar. Touches: **tui** (+ pyproject, spec).
This closes the roadmap open question **panel layout** and the tentative register row —
decision to record: **chat on the left; right column split — ledger on top, document below**
(three information surfaces, two columns), per architecture.md's tentative sketch.

**What needs to be done:**
- pyproject: `tui = ["textual>=0.80"]` optional extra; `textual` imported lazily —
  `murari tui` without the extra prints a typed install hint, everything else keeps working.
- `murari/tui.py`: `MurariApp(App)` — chat panel (log + input) left; right column: ledger
  panel above, document panel below; a footer **status bar** with style/depth, current
  role/move, runs remaining (`MURARI_RUNS` minus journal agent-moves), and idle/«копає» state.
- CLI: `murari tui [session] [--new "<тема>"] [--name] [--style] [--depth]` — the same session
  resolution as `murari chat` (reopen the most recent / create empty when bare).
- On open, panels render the current workspace state once (live refresh is MUR-019).
- Close the open question in [roadmap.md](../roadmap.md): layout decided (register row →
  ✅); update the Interface section of [architecture.md](../architecture.md).

**Dependencies:** None

**Expected result:**
`murari tui` opens a three-panel app over a session with a truthful status bar — inert but
correct; the layout decision is recorded in the specs.

**Acceptance criteria:**
- [ ] **Unit test:** the app composes chat/ledger/document panels + status bar (Textual
      `run_test()` pilot — headless, no paid calls).
- [ ] **Unit test:** session resolution matches `murari chat` (bare → most recent or empty);
      missing `textual` → typed hint, exit code 1, `murari chat`/`run` unaffected.
- [ ] **Unit test:** status bar reads style/depth and runs-remaining from config + journal.
- [ ] Roadmap register/open questions updated: layout decided (spec + code in this issue).
- [ ] Ties to roadmap §v0.3 Task "Textual three-panel layout + status bar".

---

### MUR-019 — Panels: ledger (lineage/journal) + read-only document, re-read on completion

**Description:**
The two workspace surfaces. The ledger panel renders H-ids with statuses, the lineage
**tree** (`parents`), «випробувано» marks, ★ scores, and the run journal; the document panel
renders `DOCUMENT.md` as markdown and is **read-only to the user** (accepted 2026-07-05:
document wishes are orders to Ткач through chat, never file edits). Touches: **tui**.

**What needs to be done:**
- Ledger panel: a tree/list view built from `murari.ledger` — root hypotheses with their
  descendants nested (lineage), status + ★ scores + «випробувано» inline, the journal tail
  underneath; за/проти counts from `## Аргументи`.
- Document panel: markdown rendering of `DOCUMENT.md` (empty-state text before the first
  weave); **no edit affordance** — the widget accepts no input, pinning the ownership
  invariant at the UI level.
- A `refresh_workspace()` app method: both panels re-read their files; called on session
  open, after every completed move (wired to real runs in MUR-020), and on `/ledger`.
- Graceful rendering of a malformed ledger (`LedgerError` → error line, app keeps running).

**Dependencies:** MUR-018

**Expected result:**
Panels show the live truth of `LEDGER.md`/`DOCUMENT.md` after every refresh, and the document
surface cannot be edited.

**Acceptance criteria:**
- [ ] **Unit test:** panel re-read on completion — write fake workspace files, call
      `refresh_workspace()`, assert lineage tree (a `combine` child under two parents),
      journal lines, and document text all update.
- [ ] **Unit test:** the document widget exposes no editing (read-only pinned); malformed
      ledger renders an error without crashing the app.
- [ ] Ties to roadmap §v0.3 Tasks "Ledger panel renders H-ids, lineage (tree), «випробувано»
      marks, journal" and "DOCUMENT panel read-only".

---

### MUR-020 — Async runs: worker seam, non-blocking chat, status transitions

**Description:**
The phase's heart: agent runs take minutes, so `ChatSession.turn` / `/go` dispatch moves into
a Textual **worker** while the chat input stays live. Status bar transitions idle → «копає:
<роль>» → idle; the engine's `on_progress` lines stream into the chat panel; panels refresh
on completion. Touches: **tui**. Closes the tentative register row **async run +
non-blocking chat** (→ accepted).

**What needs to be done:**
- Run every `ChatSession.turn` in a worker thread (one at a time — a second submit while a
  run is active queues or is politely refused; decide and test); the input widget never
  blocks.
- `on_progress` → thread-safe `call_from_thread` append into the chat log (the ⚙ announce
  line and the engine's per-move progress land as they happen).
- Status-bar state machine: `idle` → `копає: <роль/стиль>` (with elapsed time) → `idle`;
  failures land as chat messages (the engine already rolls back the failed move only).
- On worker completion: `refresh_workspace()` + the reply rendered into the chat log
  (visually separated, as in the REPL).
- Update the register row in [roadmap.md](../roadmap.md): async + non-blocking chat ✅.

**Dependencies:** MUR-018, MUR-019

**Expected result:**
You can keep typing while the agent digs; progress streams in live; the ledger and document
panels update the moment a move completes.

**Acceptance criteria:**
- [ ] **Integration test:** chat stays responsive during a mock run — a slow `MockAgentRunner`
      (event-gated) runs in the worker while the pilot types into the input; the queued/refused
      policy for a second submit is pinned.
- [ ] **Unit test:** status-bar state machine transitions (idle → копає → idle; failure path).
- [ ] **Integration test:** a completed mock run refreshes both panels and renders the reply.
- [ ] Roadmap register updated: async run + non-blocking chat accepted.
- [ ] Ties to roadmap §v0.3 Task "Async moves + non-blocking chat; status transitions".

---

### MUR-021 — Commands: /b, /open, /style, /go, /help, /ledger, /quit

**Description:**
The TUI command set over the v0.2 chat pipeline. `/b <тема>` starts a fresh named session in
place, `/open <session>` explicitly continues another one, and the rest reuse `ChatSession`'s
existing commands (`/style`, `/go [стиль] [глибина] [Hxx]`, `/help`, `/ledger`, `/quit`).
Touches: **tui**.

**What needs to be done:**
- Input dispatch: `/`-prefixed lines route to the command handler; everything else is a chat
  turn (the router pipeline as-is).
- `/b <тема>` — create + auto-name a fresh session (Namer flow) and switch the whole app to
  it (panels re-read, status bar resets, a fresh `ChatSession`); a fresh `/b` starts blank —
  no implicit cross-session memory.
- `/open <session-dir>` — switch to an existing session (explicit continuation); unknown dir
  → chat-line error, app keeps running.
- `/style`, `/go`, `/help`, `/ledger` — delegate to `ChatSession._command` (single source of
  command truth); `/ledger` also triggers a panel refresh; `/quit` exits the app, session dir
  remains on disk.
- `/help` line shown in the chat log on startup (same `_HELP` text + `/b`, `/open`).

**Dependencies:** MUR-018

**Expected result:**
All six roadmap commands (plus `/help`) work inside the TUI, with session switching that
re-points every panel.

**Acceptance criteria:**
- [ ] **Unit test:** command parsing — `/b`, `/open`, `/style` (incl. bad key), `/go` tokens,
      `/help`, unknown command → help; non-command lines go to the chat pipeline.
- [ ] **Unit test:** `/b` creates a named session and switches the app; `/open` continues an
      existing one (its ledger visible after refresh); `/quit` leaves the dir on disk.
- [ ] Ties to roadmap §v0.3 Task "Commands" and the DoD clauses "/style switches scenarios;
      /open continues a prior document; /quit leaves the session dir on disk".

---

### MUR-022 — Phase integration: the DoD as a driven-TUI script + docs

**Description:**
Drive the whole DoD end to end against mocks and document the surface. Touches: **tui**
(+ tests, docs). Integrates MUR-019/020/021.

**What needs to be done:**
- **Integration test (the phase DoD as a script):** with mock Haiku + `MockAgentRunner`/
  FakeAgent under the Textual pilot — `/b <тема>` opens a session; a routed chat turn runs;
  the ledger panel fills with verdicts and lineage; a weave move rebuilds the document panel;
  the chat stays usable during the run; `/style` switches; `/open` continues a prior session's
  document; `/quit` exits with the session dir intact.
- README + docs/USAGE.md: the `murari tui` section (install extra, layout, status bar,
  commands); CLAUDE.md interface note updated from "planned" to shipped for the TUI.
- Sweep: `ruff` clean; the whole suite still paid-API-free (textual pilot is local).

**Dependencies:** MUR-019, MUR-020, MUR-021

**Expected result:**
One scripted pilot run proves the v0.3 DoD, and the docs tell a new user how to open the TUI.

**Acceptance criteria:**
- [ ] **Integration test:** the full DoD script above passes headless (no paid APIs).
- [ ] README/USAGE/CLAUDE.md updated for `murari tui`.
- [ ] Ties to roadmap §v0.3 DoD in full.

---

## v0.3 scope notes

**Total effort:** ~2.5–3 weeks (M+M+L+M+S).
**Critical path:** MUR-018 → MUR-019 → MUR-020 → MUR-022.
**Phase DoD (roadmap §v0.3):** a `/b` session shows the chat, the ledger filling with verdicts
and lineage, the document rebuilding after weave moves — chat stays usable during runs;
`/style` switches scenarios; `/open` continues a prior document; `/quit` leaves the session
dir on disk.
**Contracts pinned this phase:** none of the stable seams change — the TUI only *reads* the
workspace and drives the existing `ChatSession`/Dispatcher (the single-tool boundary and
ownership invariants are re-asserted at the UI level: a read-only document widget, MUR-019).
Decisions closed: **panel layout** (MUR-018) and **async run + non-blocking chat** (MUR-020),
both recorded in the roadmap register.
**Model/mock note:** CI mocks the agent (`claude -p`), the Haiku chat model, and web search —
**no paid APIs**; TUI tests run headless under Textual's pilot.
**Companion documents:**
- [roadmap.md](../roadmap.md) — version goals, per-phase Goal/Tasks/DoD/Tests (§v0.3).
- [architecture.md](../architecture.md) — the two-head architecture, the Interface section, sandbox invariants.
- [mission.md](../mission.md) — principles and the Definition of done.
- Generated on upload: `phase3-github-report.md` (MUR-xxx → GitHub #), then `phase3-execution-report.md`.
