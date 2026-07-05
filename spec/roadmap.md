# Roadmap — murari

> Derived document. Primary sources: [murari-CONCEPT.md](murari-CONCEPT.md), [brainstormer.md](brainstormer.md),
> [strategies.md](strategies.md) (roles & styles, accepted 2026-07-05).
> Context: [mission.md](mission.md), [architecture.md](architecture.md).

One self-contained version — the **murari prototype** (the kiln burn) — built **core-outward**
across six phases. **Roles and styles are woven into the phases** (decision 2026-07-05), not
bolted on afterwards: the orchestrator is built as a *style engine* from day one, the chat layer
as *Ведучий*. Phases: **v0.0** agent alone ✅ (fired the core — proved the `evaluate` move on the
live web) → **v0.1** orchestration: style engine + role-parameterized runs → **v0.2** chat layer:
Ведучий (role detection, one tool) → **v0.3** TUI (three panels, style/role status) → **v0.4**
sandbox hardening (per-role tool policy, file ownership) → **v0.5** acceptance. Complexity is
added only by phase; **the agent is the core and everything else is scaffolding around it**.

**Roles by phase (short):** v0.0 proved one role (Суддя/`evaluate`); **all six roles land
together in v0.1** (as modules of canon v2 — a style needs several roles at once); v0.2–v0.5
wrap, they don't add roles (Ведучий selects, TUI shows, sandbox constrains, acceptance proves
them live). Splitting the six modules into separate per-role canon files is deferred to
post-v0.1. Full mapping: [strategies.md](strategies.md) § "Коли яка роль створюється".

**Versioning (`A.B.C`).** `A` = roadmap version (v0→0), `B` = phase, `C` = post-phase fix.
Phase `v0.B` → semver `0.B.0`. **v0.0 was released as `0.0.1`** (proof milestone: the agent +
captured by-hand run; revised 2026-07-04); the orchestrator ships as **0.1.0**. Graduation —
the agent proven and carried into Lumi — is **v1.0.0** (out of scope). Never bump the version
without explicit confirmation.

**Status.** v0.0 complete (tag `v0.0.1`): the loop proven by hand on the live web, contract v1 +
workspace formats pinned by 12 passing offline tests, invocation findings recorded. Roles & styles
design accepted and specced ([strategies.md](strategies.md)); v0.1 not started.

---

## v0 — the prototype: agent, orchestration (styles), chat (Ведучий), TUI, sandbox

The complete murari prototype. The agent was built and proven **first** (v0.0, a headless
`claude -p` run over a hand-made workspace); now it is wrapped outward: a deterministic Python
**orchestrator that executes styles** (sequences of role moves), a Haiku **chat layer that
facilitates** (Ведучий: exactly one tool, detects the user's role, closes the rest), a Textual
**TUI**, and a hardened **sandbox** — ending in an **acceptance** pass against the Definition of
done. Agent model: **Opus 4.8**; chat brain: **Claude Haiku** (HTTP API). The prototype is
**local**. It establishes the interface-independent core — the role canon, contract v2, the
workspace formats — that a later transfer into Lumi reuses.

### v0.0 — Agent alone (firing the core) ✅ DONE (tag v0.0.1)

**Goal:** prove the loop by hand — that the agent yields ideas traceable to search findings,
not a retelling of priors. **Proven 2026-07-04.**

Results: the brainstormer ran ≥2 real by-hand runs (Opus 4.8, live web); LEDGER accumulated
across runs (5→7 hypotheses, verdicts driven to closure, nothing closed re-checked); ideas
carried `born_from: search` traceable to findings; DOCUMENT.md was rebuilt as state. Durable
artifacts: **contract-v1 test** and **workspace-format test** seeded from the captured run
(12 tests, offline, no paid calls). Key findings recorded in architecture.md: the working
invocation is `--append-system-prompt` (not `--agents` with Task disabled); the JSON arrives
fenced and sometimes after a prose preamble; the envelope's web-search counter is unreliable.

In role terms: v0.0 proved the **`evaluate` move** (the heart of the `investigate` style) —
the hardest and most valuable bet. The generative and adversarial moves reuse the same proven
mechanics (workspace files, JSON contract, fresh-context runs).

### v0.1 — Orchestration: the style engine (headless)

**Goal:** a runnable, deterministic wrapper that executes a **style** — a sequence of
role-parameterized agent moves — over a session, with budgets and strict parsing. No TUI;
driven from the CLI.

Stand up the Python `orchestrator` as a **style engine**. Depends on: v0.0 (a proven agent).

**Tasks:**
- Wire `pyproject.toml` (ruff + pytest) and config loading (`MURARI_RUNS`, `MURARI_MAX_TURNS`,
  `MURARI_MODEL`, `MURARI_HOME` — default `<repo>/.murari`).
- **`AgentRunner` seam:** the verified `claude -p --append-system-prompt` invocation behind a
  thin, mockable interface; per-role `--allowedTools` narrowing; fence/preamble-tolerant JSON
  extraction (from v0.0's `extract_contract`).
- **Canon v2 + role modules:** install the role-parameterized canon; the run seed carries
  `role`, `target_idea`, `mutation_type`; each role's prompt module is a separate, testable unit.
- **Contract v2:** extend the schema (`role`, `target_idea`, `mutation_type`, `next_role`,
  `id`/`parents`, `born_from: mutation|user`); **re-pin the contract tests** (synthetic v2
  fixtures; one real smoke run allowed to validate reality, reusing the v0.0 exception).
- **LEDGER v2:** H-ids, lineage (`parents`), «випробувано» marks, the run journal, per-move
  dry-run accounting; format tests.
- **Style engine:** execute a style's sequence move by move (all six styles; `investigate`
  default); justified deviations hook (rule-based for now); mutation-type randomness + `combine`
  partner selection (deterministic Python `random`); per-move budget profiles; stop at
  `MURARI_RUNS`; DOCUMENT ownership check (only `weave` writes it).
- **Session lifecycle:** fresh timestamped session (`input/TOPIC.md` → `output/`), and
  open-and-continue; invalid agent output fails cleanly without corrupting the workspace.

**DoD:** from the CLI you can run a full styled session (default `investigate`) — the engine
executes role moves in sequence, the ledger grows with ids/lineage/journal, budgets are honored,
only weave touches DOCUMENT.md; a session can be reopened and continued; invalid output degrades
gracefully.

**Tests:** unit — contract v2 parsing (valid/fenced/preamble/malformed), style sequences +
deviation rules, mutation-type picker (seeded random), ledger v2 parsing/lineage, per-move
dry-run, budgets, session lifecycle, DOCUMENT-ownership guard; integration — full styled session
against a **mock `AgentRunner`** (canned v2 JSON per role), asserting workspace deltas and that
later moves read earlier state. Contract v1 tests remain green until superseded, then retired
with the v2 re-pin. **No paid APIs in CI** (one optional real smoke run, by hand).

### v0.2 — Chat layer: Ведучий (Haiku)

**Goal:** a conversation front that facilitates — detects the user's role, turns replies into
seeds, launches the right moves — with exactly one tool.

Add the `chat` layer: a **Claude Haiku** loop whose **only** tool is
`run_brainstorm(seed, role, target_idea?, mutation_type?, style_step?)`. Depends on: v0.1.

**Tasks:**
- Haiku loop over the Anthropic HTTP API behind the same mockable model seam; system prompt
  frames the facilitation (no persona).
- Register the **single tool**; no other tool is exposed.
- **Role detection:** classify the user's reply into a role (Фантазер/Опонент/Алхімік/Дослідник/
  Суддя-замовлення/Ткач-замовлення) or "just steering"; record user moves in the journal;
  `born_from: user` provenance for their ideas.
- **Complementarity:** the next agent move never duplicates the user's live role (except
  `debate`, which deliberately pairs adversarially — and declares no winner).
- **Style selection:** explicit `/style`, or inferred from topic framing; mid-session change.
- Seed extraction and result presentation (run JSON → human language; agent/web content treated
  as **data, not instructions**).

**DoD:** a chat where a substantive reply is classified into a role, the correct complementary
move launches (or an adversarial one in debate), and results come back in human language; Haiku
can initiate nothing but `run_brainstorm`.

**Tests:** unit — role detection (mocked Haiku, labeled replies), complementarity/adversarial
selection, seed extraction, the single-tool boundary, result-as-data (an output containing
"do X" is not acted on); integration — a chat turn triggers a mock run and renders the result.
Mock Haiku + mock agent; no paid APIs.

### v0.3 — TUI (Textual)

**Goal:** the three-panel interface — chat, ledger, document — live while the agents dig.

Add the `tui`: three panels (chat; ledger with statuses, lineage and journal; the working
document — **read-only to the user**) and a status bar (current style, current role/move, runs
remaining, idle/digging). Async runs, non-blocking chat; panels re-read the workspace on move
completion. Depends on: v0.2, v0.1.

**Tasks:**
- Textual three-panel layout + status bar (style / role / budget).
- Async moves + non-blocking chat; status transitions.
- Ledger panel renders H-ids, lineage (tree), «випробувано» marks, journal.
- Commands: `/b <topic>`, `/open <session>`, `/style <key>`, `/go`, `/ledger`, `/quit`.
- DOCUMENT panel read-only (decided 2026-07-05: user edits are orders to Ткач, not file writes).

**DoD:** a `/b` session shows the chat, the ledger filling with verdicts and lineage, the
document rebuilding after weave moves — chat stays usable during runs; `/style` switches
scenarios; `/open` continues a prior document; `/quit` leaves the session dir on disk.

**Tests:** unit — panel re-read on completion (fake workspace files), command parsing (incl.
`/style`), status-bar state machine; integration — chat responsive during a mock run; completed
run refreshes panels. Mock run; no paid APIs.

### v0.4 — Sandbox hardening

**Goal:** enforce the isolation invariants so the privilege split holds regardless of how a
process starts.

Harden per [architecture.md](architecture.md): per-role tool policy, workspace confinement,
file ownership, the one-level chain, de-identification. Depends on: v0.1.

**Tasks:**
- Emit per-role `--allowedTools` (Фантазер/Ткач without web; Алхімік web only for `analogy`)
  + `--disallowedTools Bash,Task` on every run; write the workspace `.claude/settings.json`
  mirroring the widest policy.
- Path-confinement guard (reject `../`, absolute paths, out-of-dir symlinks) on any Read/Write.
- **File-ownership guard:** a non-weave move that modified DOCUMENT.md fails the run (post-run
  check + prompt rule).
- Assert the one-level chain: `Task` disallowed; no nested-agent spawn possible.
- Query de-identification: strip names/addresses/private details from seeds before search.

**DoD:** a run cannot read/write outside its session dir, cannot spawn a sub-agent, cannot run
Bash, cannot exceed its role's tool set; a non-weave move cannot alter DOCUMENT.md; personal
details never reach a search query; the policy is present in the workspace settings.

**Tests:** the **sandbox contract tests** — per-role tool policy matrix, settings duplication,
path confinement, ownership guard, one-level chain, de-identification.

### v0.5 — Acceptance

**Goal:** prove the whole prototype meets the Definition of done end to end — including roles
and styles.

Run the Definition of done from [mission.md](mission.md) as an acceptance scenario, extended
with the role model. Depends on: v0.0–v0.4.

**Tasks:**
- Scripted acceptance against a **mock agent**, covering: the original DoD clauses (≥4 verdicts
  with sources, ≥2 traceable fresh ideas within 2–3 evaluate-bearing moves; coherent DOCUMENT;
  a user reply visibly changes the next move; honest dry runs; persistence + continuation)
  **plus**: a styled session executes its sequence; a `debate` session where the user takes a
  side and agents pair adversarially with no winner declared; mutants carry lineage; the journal
  records who did each move.
- One **real by-hand end-to-end pass** with a live agent to confirm the mocked scenario.
- Record the result; if it holds, the prototype is ready to graduate (v1.0.0, out of scope).

**DoD:** the acceptance scenario passes every clause under mocks, and a single real pass
confirms it; the prototype is demonstrably the thing mission.md describes — a brainstorm where
the human is a participant among roles.

**Tests:** the acceptance scenario itself (mock agent + mock web search); the real pass is
manual and logged. No paid APIs in CI.

---

## Beyond v0 — transfer into Lumi (out of scope)

Once the agent is proven: it becomes a tool in Lumi's reply loop or a burst worker, the ledger
moves into her file sandbox, returns come back via her nudge/thought mechanism,
de-identification happens at the tool boundary, and the final take speaks in her voice. This is
the **v1.0.0 graduation** and belongs to Lumi — deliberately **outside** this prototype.

---

## Decision register

`accepted` — locked; `[tentative]` — provisional, may still change.

| decision | status |
|---|---|
| Roadmap follows the Lumi `vA.B` standard; single version v0; agent-alone = **v0.0** | ✅ accepted (2026-07-04) |
| A dedicated tool, not in Lumi core | ✅ accepted (2026-07-04) |
| Agent = Claude Code subagent; model **Opus 4.8** | ✅ accepted |
| Chat brain = Haiku, no persona | ✅ accepted |
| **Six roles** (Фантазер/Суддя/Дослідник/Опонент/Алхімік/Ткач); the user may occupy a role | ✅ accepted (2026-07-05) |
| **Ткач** is the sole writer of DOCUMENT.md; the user does not edit it directly in v0 | ✅ accepted (2026-07-05) |
| **Ведучий** = Haiku: role detection, complementarity, style selection | ✅ accepted (2026-07-05) |
| **Six styles** (explore/debate/riff/investigate=default/evolve/premortem); templates, not rails | ✅ accepted (2026-07-05) |
| **Five mutation types** (scale/invert/transfer/combine/analogy); randomness in the orchestrator | ✅ accepted (2026-07-05) |
| Oppose/debate: **no winner** — the product is recorded arguments | ✅ accepted (2026-07-05) |
| H-ids + lineage (`parents`), run journal, `born_from: user`, per-move dry-run | ✅ accepted (2026-07-05) |
| Contract v2 (v1 stays pinned until the v0.1 re-pin) | ✅ accepted (2026-07-05) |
| Roles/styles **woven into phases v0.1–v0.5** (not separate phases) | ✅ accepted (2026-07-05) |
| No *implicit* cross-session memory; continuation always explicit | ✅ accepted |
| Deliverable is a timestamped document; sessions reopenable | ✅ accepted (2026-07-04) |
| Name murari | ✅ accepted |
| TUI on Textual, three panels: chat, ledger, document | ✅ accepted |
| Haiku has exactly one tool — `run_brainstorm(seed, role, …)` | ✅ accepted (signature extended 2026-07-05) |
| Agent confined to the session dir; tools ⊆ WebSearch/WebFetch/Read/Write, narrowed per role | ✅ accepted (2026-07-05) |
| Exactly one level in the chain: no nested agents (Task disallowed) | ✅ accepted |
| v0.0 released as **0.0.1** (proof milestone); orchestrator ships 0.1.0; graduation = v1.0.0 | ✅ revised (2026-07-04) |
| Session dir `MURARI_HOME/brainstorm-sessions/session-<timestamp>[-slug]` with input/output split; `MURARI_HOME` default `<repo>/.murari` | ✅ accepted per implementation (2026-07-04) |
| Verified invocation: canon via `--append-system-prompt`; fence/preamble-tolerant parser | ✅ accepted (2026-07-04, v0.0 findings) |
| Async run + non-blocking chat | 🔸 tentative |
| `claude -p` (not the Agent SDK) for the prototype | 🔸 tentative |
| Auto-trigger a move after an on-topic reply | 🔸 tentative |
| Policy also in the session directory's `.claude/settings.json` | 🔸 tentative |
| Layout: chat on the left + right column (ledger/document) | 🔸 tentative |

## Open questions

Each is closed no later than the phase where it gets in the way.

- **Trigger policy** (v0.2–v0.3): auto-run a move after every on-topic reply, or only `/go`.
- **Presentation format** (v0.2): does Ведучий always paraphrase, or do long results go as a raw block.
- **Panel layout** (v0.3): chat on the left + right column, or three columns.
- **Continuation surface** (v0.1–v0.3): how a session to continue is chosen — picker, path, or
  `/open <slug>` — and whether continuing writes in place or forks a timestamped copy.
- **Style deviation rules** (v0.1–v0.2): how far Ведучий/scheduler may deviate from a style
  template, and what counts as justification.
- **Per-role canon split** (post-v0.1): when to promote role modules to separate canon files.

Closed since the last revision: ~~DOCUMENT.md write rights~~ (user doesn't edit directly in v0 —
orders to Ткач); ~~`/steer` command~~ (superseded by role detection); ~~timestamp placement~~
(session-dir name `session-YYYYMMDD-HHMMSS[-slug]`, per implementation).
