# Phase v0.0 — GitHub Issues

Issues for phase **v0.0 — Agent alone (firing the core)** (version **v0 — the prototype**),
derived from the per-phase Goal / Tasks / DoD / Tests in [roadmap.md](../roadmap.md) (§v0.0)
and the contracts in [architecture.md](../architecture.md). This is the **first** phase;
IDs start at **MUR-001…MUR-005** and continue into later phase files.

v0.0 fires the core with no scaffolding: install the brainstormer agent, hand-write a
`TOPIC.md`, and run `claude -p` under the sandbox invariants for several runs — proving
the diverge→verify→synthesize loop yields ideas traceable to search findings, not a
retelling of priors. It is the one place a **real model call** is warranted (the point of
the phase is to prove the agent itself); the durable artifacts are two tests seeded from
the captured run that pin the **JSON output** and **workspace-format** seams every later
phase depends on. **Until the DoD here holds, v0.1 does not start.**

## Issues Summary Table

| # | ID | Title | Size | Area | Phase | Dependencies |
|---|----|-------|------|------|-------|--------------|
| 1 | MUR-001 | Install the brainstormer agent | S | agent | p0 | -- |
| 2 | MUR-002 | Hand-written test session workspace (TOPIC.md) | S | tests | p0 | -- |
| 3 | MUR-003 | By-hand run: fire the loop and capture artifacts | M | agent | p0 | MUR-001, MUR-002 |
| 4 | MUR-004 | Contract test: pin the agent JSON output schema | S | tests | p0 | MUR-003 |
| 5 | MUR-005 | Workspace-format test: pin LEDGER structure + dry-run counter | M | tests | p0 | MUR-003 |

**Size legend:** S = 1–2 days, M = 3–5 days, L = 5–8 days
**Area:** agent · chat · tui · orchestrator · sandbox · tests · spec

---

## Dependency Tree

```
MUR-001 (install agent) --+
                          +--> MUR-003 (by-hand run + capture) --+--> MUR-004 (JSON contract test)
MUR-002 (TOPIC.md) -------+                                      |
                                                                 +--> MUR-005 (workspace-format test)
                                                                        => v0.0 DoD (loop proven by hand,
                                                                           two seams pinned)
```

**Parallelization hints:** MUR-001 and MUR-002 have no dependencies — do them in parallel.
Both gate MUR-003 (the real, paid by-hand run). Once MUR-003's artifacts are captured,
MUR-004 and MUR-005 run in parallel.

---

## v0.0 — Agent alone (firing the core)

### MUR-001 — Install the brainstormer agent

**Description:**
Install the brainstormer canon as `.claude/agents/brainstormer.md` so
`claude -p --agents brainstormer` resolves to the Opus-4.8 agent with the closed tool
quartet. Touches: **agent**. This is the phase gate — every later v0.0 step runs this agent.

**What needs to be done:**
- Copy the canon from [spec/brainstormer.md](../brainstormer.md) verbatim to `.claude/agents/brainstormer.md` (the spec file is the source of truth).
- Verify the YAML frontmatter is the agent frontmatter: `name: brainstormer`, `tools: WebSearch, WebFetch, Read, Write`, `model: opus`.
- Confirm the agent resolves by name via a trivial headless invocation (it loads without error).

**Dependencies:** None

**Expected result:**
`.claude/agents/brainstormer.md` exists and `claude -p --agents brainstormer` loads the Opus-4.8 brainstormer with exactly the four allowed tools.

**Acceptance criteria:**
- [ ] `.claude/agents/brainstormer.md` matches `spec/brainstormer.md` (canon is the source of truth).
- [ ] Frontmatter declares `tools: WebSearch, WebFetch, Read, Write` and `model: opus` — the closed quartet, no Bash/Task.
- [ ] `claude -p --agents brainstormer …` resolves the agent (a trivial dry invocation loads it without error).
- [ ] Ties to DoD: the agent used by the by-hand run (MUR-003) exists and is the canonical one.

---

### MUR-002 — Hand-written test session workspace (TOPIC.md)

**Description:**
Create a test session directory whose only file is a hand-written `TOPIC.md` (topic + seeds,
in Ukrainian) — the input for the by-hand run and the seed fixture for the later tests.
Touches: **tests** (fixture). The agent creates the rest of the workspace on its first run;
only `TOPIC.md` is authored here, and it is read-only to the agent.

**What needs to be done:**
- Create a session directory under a fixtures path (e.g. `tests/fixtures/session-<timestamp>-<slug>/`) containing only `TOPIC.md`.
- Write `TOPIC.md` in Ukrainian: a concrete topic plus 1–2 seeds that have a **factual core the live web can confirm or refute** (so the agent's `select`/`verify` steps can produce sourced verdicts).
- Leave `LEDGER.md` / `SOURCES.md` / `IDEAS.md` / `DOCUMENT.md` **absent** — the agent creates them on the first run (this exercises the first-run branch of the cycle).

**Dependencies:** None

**Expected result:**
A ready-to-run session directory whose only file is a hand-written Ukrainian `TOPIC.md` with a verifiable topic and seeds.

**Acceptance criteria:**
- [ ] `TOPIC.md` is present, Ukrainian, with a factually verifiable topic + seeds; no other workspace files exist (the agent creates them).
- [ ] The topic/seeds have a factual core the web can check, so `verify` can yield sourced verdicts (not purely speculative).
- [ ] Ties to DoD: this workspace is the input that lets a by-hand session reach the Definition of done.

---

### MUR-003 — By-hand run: fire the loop and capture artifacts

**Description:**
The prototype's main bet — run the brainstormer over the test session **by hand** for
several runs and capture the artifacts. Touches: **agent**. This is the one deliberate
real-model, **paid** run in the whole project (every later phase mocks it); the point is to
prove the agent itself.

**What needs to be done:**
- Run `claude -p --agents brainstormer --allowedTools WebSearch,WebFetch,Read,Write --disallowedTools Bash,Task --max-turns N --output-format json` with `cwd` = the MUR-002 session directory.
- Repeat for **several runs in a row** (≥2) so state accumulates; watch `LEDGER.md` grow and `DOCUMENT.md` get rebuilt between runs.
- Capture and commit as fixtures: one run's **raw JSON output**, and the resulting `LEDGER.md` / `SOURCES.md` / `IDEAS.md` / `DOCUMENT.md` after the multi-run sequence (enough to show accumulation).
- Record the exact invocation and run count for reproducibility.

**Dependencies:** MUR-001, MUR-002

**Expected result:**
A captured, committed set of real-run artifacts (JSON output + workspace files across ≥2 runs) that demonstrably meet the phase DoD and seed the two tests.

**Acceptance criteria:**
- [ ] A real by-hand session runs the agent ≥2 times over the MUR-002 workspace — the **deliberate paid exception** (no mocks here; this is the phase's own test per roadmap §v0.0).
- [ ] Captured JSON output is valid against the output contract `{hypotheses, fresh_ideas, next_probes, document_delta, dry_run}` (status enum `open|confirmed|refuted|partial`, `source: url|null`).
- [ ] `LEDGER.md` accumulates across runs — closed (`confirmed`/`refuted`) hypotheses are not re-checked; the dry-run counter is present.
- [ ] ≥1 idea carries `born_from: search` with a `basis` traceable to a specific finding; `DOCUMENT.md` reads as rebuilt state, not an appended log.
- [ ] Artifacts committed as fixtures for MUR-004 / MUR-005.
- [ ] Ties to DoD: this is the by-hand proof that the loop yields source-traceable ideas — **until this holds, v0.1 does not start**.

---

### MUR-004 — Contract test: pin the agent JSON output schema

**Description:**
Seed a contract test from the MUR-003 capture that validates the agent's JSON output against
its schema. Touches: **tests** (+ `spec/architecture.md` if the capture reveals a
discrepancy). This pins the **output-contract seam** every later phase depends on.

**What needs to be done:**
- Define the JSON schema for `{hypotheses[], fresh_ideas[], next_probes[], document_delta, dry_run}` with the hypothesis status enum `open|confirmed|refuted|partial` and `source: url|null`, matching [architecture.md](../architecture.md) §Output contract.
- Write a `pytest` contract test that loads the captured JSON (MUR-003) and asserts it validates; add a couple of malformed variants that must fail.
- Run under a **bare `pytest tests/`** — the full `pyproject.toml` / ruff / CI wiring is v0.1; do not pull it in here.
- If the captured run diverges from the documented schema, update `spec/architecture.md` (and the agent canon if the output shape changed) **in this same issue**.

**Dependencies:** MUR-003

**Expected result:**
A committed contract test that pins the agent JSON output schema and passes against the captured run.

**Acceptance criteria:**
- [ ] **Contract test:** the JSON output schema `{hypotheses, fresh_ideas, next_probes, document_delta, dry_run}` + status enum is pinned and passes on the captured JSON; malformed variants fail.
- [ ] Schema matches `spec/architecture.md` §Output contract (seam = architecture + test together; any divergence updates architecture.md here).
- [ ] Runs under `pytest tests/` without project-level config (pyproject deferred to v0.1).
- [ ] Ties to phase Tests: the durable "contract test pinning the JSON output schema" named in roadmap §v0.0.

---

### MUR-005 — Workspace-format test: pin LEDGER structure + dry-run counter

**Description:**
Seed a workspace-format test from the MUR-003 capture that pins the `LEDGER.md` structure and
the dry-run counter, and encodes the DoD-level accumulation/traceability checks. Touches:
**tests** (+ `spec/brainstormer.md` / `spec/architecture.md` if the capture diverges). Pins the
**workspace-file-format seam**.

**What needs to be done:**
- Write a `pytest` test that parses the captured `LEDGER.md`: the `## Гіпотези` section with `[status]` entries + `— джерело: url`, and the `## Сухі прогони поспіль: N` counter — matching the format in [brainstormer.md](../brainstormer.md) / [architecture.md](../architecture.md).
- Assert accumulation across the ≥2 captured runs: closed hypotheses persist and are not re-opened or re-checked; the dry-run counter holds/advances correctly.
- Assert `IDEAS.md` carries a `born_from: search` idea with a `basis`, and `DOCUMENT.md` is rebuilt state, not a per-run log.
- Run under a **bare `pytest tests/`**; if the capture diverges from the documented format, update the canon / architecture.md **in this same issue**.

**Dependencies:** MUR-003

**Expected result:**
A committed workspace-format test that pins the `LEDGER.md` structure + dry-run counter and encodes the DoD accumulation/traceability checks.

**Acceptance criteria:**
- [ ] **Contract test:** `LEDGER.md` structure (statuses, source lines) + the `Сухі прогони поспіль` counter are pinned and pass on the captured workspace.
- [ ] Accumulation asserted: closed (`confirmed`/`refuted`) hypotheses are not re-checked across runs.
- [ ] `IDEAS.md` has ≥1 `born_from: search` with `basis`; `DOCUMENT.md` is rebuilt state, not an appended log.
- [ ] Runs under `pytest tests/` (pyproject deferred to v0.1); any format divergence updates `spec/brainstormer.md` / `spec/architecture.md` here.
- [ ] Ties to phase Tests: the durable "workspace-format test (LEDGER.md structure + dry-run counter)" named in roadmap §v0.0.

---

## v0.0 scope notes

**Total effort:** ~2 weeks — dominated by the iterative real-model by-hand run (MUR-003); the install, fixture, and two tests are each S–M.
**Critical path:** MUR-001 → MUR-003 → MUR-004 / MUR-005.
**Phase DoD (roadmap §v0.0):** a by-hand session yields a result at the Definition-of-done level — the JSON is valid against the schema; `LEDGER.md` accumulates state across runs (no re-checking closed hypotheses); ≥1 idea carries `born_from: search` traceable to a specific finding; `DOCUMENT.md` is rebuilt (state), not appended to (a log). Until this holds, do not go further.
**Contracts pinned this phase:** the agent **JSON output schema** (MUR-004) and the **`LEDGER.md` format + dry-run counter** (MUR-005) — both seeded from the captured real run.
**Testing — same pattern as kiln:** kiln puts the model behind a `Brain` seam with two impls — `LiveBrain` (real: Haiku via the Messages API, Opus via `claude -p`) and `MockBrain` (canned replies) — and **all tests go through `MockBrain` → deterministic, zero paid calls** (see [kiln/brain.py](../../../kiln/kiln/brain.py)). murari copies this: from v0.1 on there is an `AgentRunner`/`Brain`-style seam with a `MockBrain` equivalent, so every test runs offline on fixed canned output. v0.0 has no app or seam yet, so its two tests run **offline against the committed captured fixtures** from the by-hand run — same result: deterministic, zero paid calls. Billing split (also kiln's): **Opus (the agent) only ever via `claude -p` / your MAX — never the API key; Haiku (the chat brain) via the Messages API.** Neither is called in tests.
**Companion documents:**
- [roadmap.md](../roadmap.md) — version goals, per-phase Goal/Tasks/DoD/Tests (§v0.0).
- [architecture.md](../architecture.md) — the two-head architecture, the one-run cycle, the output contract, sandbox invariants.
- [mission.md](../mission.md) — the values (source over confidence, freshness over erudition) and the Definition of done.
- [brainstormer.md](../brainstormer.md) — the agent canon (cycle, statuses, workspace file formats, output contract, boundaries).
- Generated on upload: `phase0-github-report.md` (MUR-xxx → GitHub #), then `phase0-execution-report.md`.
