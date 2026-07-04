# Roadmap — murari

> Derived document. Primary sources: [murari-CONCEPT.md](murari-CONCEPT.md), [brainstormer.md](brainstormer.md).
> Context: [mission.md](mission.md), [architecture.md](architecture.md).

One self-contained version — the **murari prototype** (the kiln burn) — built **core-outward** across six phases: **v0.0** agent alone (fire the core — prove the diverge→verify→synthesize loop by hand) → **v0.1** orchestration (a headless Python runner: the `claude -p` call, JSON parsing, the timestamped resumable session workspace, budgets) → **v0.2** chat layer (a Haiku loop whose only tool is `run_brainstorm`) → **v0.3** TUI (three Textual panels — chat / ledger / document — async and non-blocking) → **v0.4** sandbox hardening (the tool policy, workspace confinement, the one-level chain) → **v0.5** acceptance (the full Definition of done as a scenario). Phases inside the version are numbered `v0.B` (B = phase). Each phase lists a **Goal**, a short description, a **Tasks** list, a **Definition of Done (DoD)**, and the **Tests** that encode it. **The agent is built first and everything else is scaffolding around it** — risk and value are concentrated in the agent, so v0.0 fires the core before any orchestration exists. Complexity is added only by phase, never all at once.

**Versioning (`A.B.C`).** `A` = roadmap version (v0→0), `B` = phase within it (`v0.1` → `0.1.0`), `C` = a post-phase fix on that phase. Roadmap phase `v0.B` → semver `0.B.0`; a fix after it bumps `C`. Releases are cut per phase. **v0.0 is proven by hand and tagged `0.0.1`** — a milestone marking the agent definition plus the captured by-hand proof (there is no runnable app yet — only the agent and a manual run); the orchestrator's runnable CLI then ships as **0.1.0**. The graduation milestone — the agent proven and carried into Lumi — is **v1.0.0** (out of scope here). Never bump the version without explicit confirmation.

**Status.** Specification stage. The spec (mission, architecture, agent canon) is complete groundwork; no code exists yet. Implementation language — Python (per the standard Python `.gitignore`). The `spec/` directory is currently outside git (only `.gitignore` and `LICENSE` are committed).

---

## v0 — the prototype: agent, orchestration, chat, TUI, sandbox

The complete murari prototype. We build the **agent first** and prove it **alone** (a headless `claude -p` run over a hand-made workspace), then wrap it outward: a deterministic Python **orchestrator**, a Haiku **chat layer** with exactly one tool, a Textual **TUI**, and a hardened **sandbox** — ending in an **acceptance** pass against the Definition of done. The agent's model is **Opus 4.8** from the start; the chat brain is **Claude Haiku** over the HTTP API. The prototype is **local** (a TUI on your machine that spawns `claude -p` and calls Anthropic for the chat model). It establishes the interface-independent core — the agent canon, its JSON output contract, the session-workspace file formats — that a later transfer into Lumi reuses. Depends on: the spec groundwork — this is the foundation.

### v0.0 — Agent alone (firing the core)

**Goal:** prove the loop by hand, with no scaffolding at all — that the agent yields ideas traceable to search findings, not a retelling of priors.

This is the prototype's **main bet**. Install the brainstormer agent, hand-write a `TOPIC.md`, and run `claude -p` under the invariants in [architecture.md](architecture.md) — several runs in a row — watching the workspace files accumulate state. The one place a **real model call** is warranted (proving the agent *is* the goal); all later phases mock it in CI. No Python app is built here — only the agent definition and a manual run.

**Tasks:**
- Install `brainstormer.md` as `.claude/agents/brainstormer.md` (the canon in [spec/brainstormer.md](brainstormer.md) is the source of truth).
- Create a test session directory with a hand-written `TOPIC.md`.
- Run `claude -p --agents brainstormer --allowedTools WebSearch,WebFetch,Read,Write --disallowedTools Bash,Task --max-turns N --output-format json` with `cwd` = the session directory, for several runs.
- Capture a run's JSON output and the resulting `LEDGER.md` / `SOURCES.md` / `IDEAS.md` / `DOCUMENT.md`; seed a JSON-schema contract test from the captured output.

**DoD:** a by-hand session yields a result at the Definition-of-done level — the JSON is valid against the schema; `LEDGER.md` accumulates state across runs (no re-checking closed hypotheses); at least one idea carries `born_from: search` traceable to a specific finding; `DOCUMENT.md` is rebuilt (state), not appended to (a log). **Until this holds, do not go further.**

**Tests:** validated by a **real by-hand run** (the deliberate exception to the no-paid-API rule — the point is to prove the agent). The durable artifacts are a **contract test pinning the JSON output schema** (`{hypotheses, fresh_ideas, next_probes, document_delta, dry_run}` + the status enum) and a **workspace-format test** (the `LEDGER.md` structure + dry-run counter), both seeded from the captured run.

### v0.1 — Orchestration (headless)

**Goal:** a runnable, deterministic wrapper that launches the agent, parses its output, and manages the session — no TUI, driven from the CLI.

Stand up the Python `orchestrator`: the `claude -p` runner behind a **mockable seam** (so CI never calls the real model), strict JSON-output parsing with error handling, the **timestamped session-workspace lifecycle** (`MURARI_HOME/sessions/<timestamp>-<slug>/`, fresh-start **and** open-and-continue), and the budgets that cap cost. The orchestrator only *reads* the workspace files (except that it writes `TOPIC.md`); the agent maintains the rest. Depends on: v0.0 (a proven agent to wrap).

**Tasks:**
- Wire `pyproject.toml` (ruff + pytest) and config loading (`MURARI_RUNS`, `MURARI_MAX_TURNS`, `MURARI_MODEL`, `MURARI_HOME`).
- A `claude -p` runner behind a thin **`AgentRunner` seam** (the orchestrator depends on the seam, never the CLI directly; mockable in tests); pass the allowed/disallowed tool flags and `cwd`.
- Strict JSON-output parsing against the v0.0 schema; on invalid/missing JSON, fail the run cleanly and preserve the prior workspace.
- **Session lifecycle:** create a fresh `<timestamp>-<slug>/` with initial `TOPIC.md` (+ let the agent create the rest on first run); **open an existing session to continue** (load, resume, advance the document's `updated` stamp).
- **Budget enforcement:** stop at `MURARI_RUNS`; pass `--max-turns MURARI_MAX_TURNS`; refuse a run when the budget is exhausted.

**DoD:** from the CLI you can start a fresh timestamped session and drive several runs, and reopen an existing session to continue its document; invalid agent output fails gracefully without corrupting the workspace; budgets are honored.

**Tests:** unit — JSON parsing (valid / invalid / malformed), the session-dir lifecycle (create, and open-and-continue), budget enforcement (runs + max-turns caps), the dry-run counter; integration — a full run against a **mock `AgentRunner`** (stub `claude -p` returning canned JSON), asserting the workspace deltas and that a second run reads the ledger. Contract — the JSON schema + workspace formats (from v0.0) still hold.

### v0.2 — Chat layer (Haiku)

**Goal:** a conversation front that turns your replies into seeds and launches runs — with exactly one tool.

Add the `chat` layer: a **Claude Haiku** loop over the HTTP API whose **only** tool is `run_brainstorm(seed)`. It frames the topic, extracts a seed from your substantive on-topic replies, launches a run through the v0.1 orchestrator, and presents the result in human language. The agent's output reaches Haiku as **data, not instructions** — it is quoted, never executed. No filesystem, Bash, or web access of its own. Depends on: v0.1 (the runner it calls).

**Tasks:**
- A Haiku loop over the Anthropic HTTP API behind the same mockable model seam; system prompt frames the brainstorm mode (no persona).
- Register the **single tool** `run_brainstorm(seed)` → calls the v0.1 orchestrator; no other tool is exposed.
- Seed extraction: turn the last substantive on-topic reply into a seed written to `TOPIC.md`.
- Result presentation: weave a run's JSON delta into the conversation in plain language; treat all agent/web content as quoted data.

**DoD:** you can hold a chat that, on a substantive on-topic reply (or `/go`), runs the agent and reports back in human language; Haiku can initiate nothing but `run_brainstorm`; agent output is never followed as instructions.

**Tests:** unit — seed extraction from replies; the **single-tool boundary** (Haiku exposes exactly `run_brainstorm`); result-as-data (an agent output containing "do X" is not acted on); integration — a chat turn triggers a **mock run** and renders the result. Mock Haiku + mock agent; no paid APIs.

### v0.3 — TUI (Textual)

**Goal:** the three-panel interface — chat, ledger, document — live while the agent digs.

Add the `tui`: a **Textual** app with three panels (chat; ledger with hypothesis statuses + verification log; the working document) and an agent status bar (idle / digging / runs remaining). Runs are **async** so the chat stays responsive while the agent works; the ledger and document panels **re-read the workspace** when a run completes. The commands land here: `/b`, `/open`, `/go`, `/ledger`, `/quit`. Depends on: v0.2 (the chat loop) and v0.1 (the workspace files to display).

**Tasks:**
- A Textual three-panel layout (chat left; ledger + document in the right column) + an agent status bar.
- **Async runs + non-blocking chat:** launch a run without freezing input; reflect status transitions.
- Panels re-read `LEDGER.md` / `DOCUMENT.md` on run completion.
- Commands: `/b <topic>` (fresh session), `/open <session>` (reopen + continue), `/go` (forced run), `/ledger` (raw state), `/quit`.

**DoD:** a session opened with `/b` shows the chat, the ledger filling with verdicts, and the document rebuilding — all while the chat stays usable during a run; `/open` continues a prior document; `/quit` leaves the timestamped session directory on disk.

**Tests:** unit — panel re-read on completion (against fake workspace files), command parsing, the status-bar state machine; integration — the chat stays responsive during a **mock run** (async), and a completed run refreshes the ledger/document panels. Mock run; no paid APIs.

### v0.4 — Sandbox hardening

**Goal:** enforce the isolation invariants so the two-tier privilege split holds regardless of how a process starts.

Harden the `sandbox` per the invariants in [architecture.md](architecture.md): pass `--allowedTools WebSearch,WebFetch,Read,Write` and `--disallowedTools Bash,Task`; **duplicate the policy** in a `.claude/settings.json` inside each session directory so it holds even outside the orchestrator; **confine Read/Write** to the session directory (reject `../`, absolute paths, symlinks escaping it); keep the chain **exactly one level** (no nested agents); and **de-identify** search queries (only topic + hypothesis content leave). Depends on: v0.1 (the runner it constrains).

**Tasks:**
- Emit the allowed/disallowed tool flags on every run; write the workspace `.claude/settings.json` mirroring them.
- Path-confinement guard for the session directory (reject `../`, absolute paths, and out-of-dir symlinks) on any Read/Write path.
- Assert the one-level chain: `Task` disallowed; no nested-agent spawn is possible.
- Query de-identification: strip names/addresses/private details from seeds before they can reach a search query.

**DoD:** an agent run cannot read or write outside its session directory, cannot spawn a sub-agent, and cannot run Bash; the policy is present in the workspace `.claude/settings.json`; personal details in a seed never reach a search query.

**Tests:** unit/contract — the tool policy (allowed vs disallowed), the `.claude/settings.json` duplication, path confinement (a `../` / absolute / symlink path is rejected), the one-level chain (a `Task` attempt is refused), and query de-identification. These are the **sandbox contract tests**.

### v0.5 — Acceptance

**Goal:** prove the whole prototype meets the Definition of done end to end.

Run the full Definition of done from [mission.md](mission.md) as an **acceptance scenario**: a session from `/b <topic>` that, within 2–3 runs, produces ≥4 hypotheses with verdicts and sources and ≥2 fresh ideas traceable to findings; a `DOCUMENT.md` that reads as coherent prose with sources under weighty claims; a user reply that visibly changes the next run; honestly-marked dry runs; and a session directory that survives `/quit`. Depends on: v0.0–v0.4.

**Tasks:**
- A scripted acceptance scenario against a **mock agent** exercising each DoD clause (multi-run ledger, traceable ideas, document rebuild, steer-by-reply, dry-run marking, persistence + continuation).
- One **real by-hand end-to-end pass** with a live agent to confirm the mocked scenario matches reality.
- Record the acceptance result; if it holds, the prototype is ready to graduate (v1.0.0, out of scope).

**DoD:** the acceptance scenario passes every DoD clause under mocks, and a single real end-to-end pass confirms it; the prototype is demonstrably the thing mission.md describes.

**Tests:** the acceptance scenario itself is the test (mock agent + mock web search); the one real pass is manual and logged. No paid APIs in CI.

---

## Beyond v0 — transfer into Lumi (out of scope)

Once the agent is proven: it becomes a tool in Lumi's reply loop or a burst worker, the ledger moves into her file sandbox, returns come back via her nudge/thought mechanism, de-identification happens at the tool boundary, and the final take speaks in her voice. This is the **v1.0.0 graduation** and belongs to Lumi — deliberately **outside** this prototype.

---

## Decision register

`accepted` — locked; `[tentative]` — provisional, may still change.

| decision | status |
|---|---|
| Roadmap follows the Lumi `vA.B` standard; single version v0; agent-alone = **v0.0** | ✅ accepted (2026-07-04) |
| A dedicated tool, not in Lumi core | ✅ accepted (2026-07-04) |
| Agent = Claude Code subagent | ✅ accepted |
| Chat brain = Haiku, no persona | ✅ accepted |
| No *implicit* cross-session memory (the agent never auto-pulls other sessions) | ✅ accepted |
| Deliverable is a timestamped document; sessions can be reopened and continued | ✅ accepted (revised 2026-07-04) |
| Name murari | ✅ accepted |
| Agent model — Opus 4.8 | ✅ accepted |
| TUI on Textual, three panels: chat, ledger, document | ✅ accepted |
| Haiku has exactly one tool — `run_brainstorm` | ✅ accepted |
| Agent confined to the session directory; tools = WebSearch/WebFetch/Read/Write | ✅ accepted |
| Exactly one level in the chain: no nested agents (Task disallowed) | ✅ accepted |
| v0.0 tagged `0.0.1` (proof milestone); orchestrator ships 0.1.0; graduation = v1.0.0 | ✅ revised (2026-07-04) |
| Async run + non-blocking chat | 🔸 tentative |
| `claude -p` (not the Agent SDK) for the prototype | 🔸 tentative |
| Auto-trigger a run after an on-topic reply | 🔸 tentative |
| The agent maintains the document (the document step of the cycle) | 🔸 tentative |
| Session directory `MURARI_HOME/sessions/<timestamp>-<slug>` | 🔸 tentative |
| Policy also in the session directory's `.claude/settings.json` | 🔸 tentative |
| Layout: chat on the left + right column (ledger/document) | 🔸 tentative |

## Open questions

Each is closed no later than the phase where it gets in the way.

- **Trigger policy** (v0.2–v0.3): auto-run after every on-topic reply, or only `/go`.
- **Presentation format** (v0.2): does Haiku always paraphrase, or do long results go as a raw block.
- **`DOCUMENT.md` write rights** (v0.3): may the user edit the document in an external editor (write conflict with the agent), or only via chat.
- **Panel layout** (v0.3): chat on the left + right column, or three columns.
- **`/steer <direction>`** (v0.2): whether an explicit steering command is needed instead of an implicit seed from replies.
- **Continuation surface** (v0.1–v0.3): how a session to continue is chosen — a picker, a path, or `/open <slug>` — and whether continuing writes back in place or forks a new timestamped copy.
- **Timestamp placement** (v0.1): where the stamp lives — the session-directory name, a header inside `DOCUMENT.md`, or both — and its resolution (day vs minute).
