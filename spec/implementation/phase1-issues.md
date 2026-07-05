# Phase v0.1 — GitHub Issues

Issues for phase **v0.1 — Orchestration: the style engine (headless)** (version **v0 — the
prototype**), derived from the per-phase Goal / Tasks / DoD / Tests in
[roadmap.md](../roadmap.md) (§v0.1) and the contracts in [architecture.md](../architecture.md)
and [strategies.md](../strategies.md) (roles & styles, accepted 2026-07-05). This file is scoped
to a single phase; IDs continue from the previous phase (MUR-005 → **MUR-006…MUR-011**).

v0.1 wraps the proven agent (v0.0) in a deterministic Python **style engine**: role-parameterized
runs behind an `AgentRunner` seam, contract **v2** (re-pinned from v1), LEDGER **v2**
(H-ids/lineage/journal), session lifecycle, budgets — driven from the CLI, no TUI. This is where
the roles-and-styles design becomes runnable code; the chat layer (Ведучий) builds on it in v0.2.

## Issues Summary Table

| # | ID | Title | Size | Area | Phase | Dependencies |
|---|----|-------|------|------|-------|--------------|
| 1 | MUR-006 | Project scaffolding: pyproject, package layout, config | S | orchestrator | p1 | -- |
| 2 | MUR-007 | Canon v2 install + contract v2 re-pin | M | agent | p1 | MUR-006 |
| 3 | MUR-008 | LEDGER v2: parser, lineage, journal, per-move dry-run | M | orchestrator | p1 | MUR-006, MUR-007 |
| 4 | MUR-009 | AgentRunner seam: verified invocation, per-role tools, mock | M | orchestrator | p1 | MUR-006, MUR-007 |
| 5 | MUR-010 | Session lifecycle: create, open-and-continue, graceful failure | S | orchestrator | p1 | MUR-006 |
| 6 | MUR-011 | Style engine + CLI: sequences, randomness, budgets, ownership | L | orchestrator | p1 | MUR-008, MUR-009, MUR-010 |

**Size legend:** S = 1–2 days, M = 3–5 days, L = 5–8 days
**Area:** agent · chat · tui · orchestrator · sandbox · tests · spec

---

## Dependency Tree

```
MUR-006 (scaffolding: pyproject + package + config)
  |
  +-- MUR-007 (canon v2 + contract v2) --+-- MUR-008 (LEDGER v2) ----+
  |                                      |                           |
  |                                      +-- MUR-009 (AgentRunner) --+
  |                                                                  |
  +-- MUR-010 (session lifecycle) -----------------------------------+
                                                                     |
                                          MUR-011 (style engine + CLI)
                                            => v0.1 DoD (full styled session from the CLI)
```

**Parallelization hints:** MUR-006 first (gate). MUR-007 next (both remaining tracks need the
v2 contract). Then MUR-008, MUR-009, MUR-010 in parallel. MUR-011 integrates everything.

---

## v0.1 — Orchestration: the style engine (headless)

### MUR-006 — Project scaffolding: pyproject, package layout, config

**Description:**
Turn the repo from specs-plus-scripts into a Python project: `pyproject.toml` (pytest + ruff
wired), the `murari/` package skeleton, and config loading. Touches: **orchestrator**. This is
the phase gate — every other issue lands code inside this structure.

**What needs to be done:**
- `pyproject.toml`: project metadata, `pytest` + `ruff` configuration (line length, target
  Python), no runtime deps beyond stdlib for now.
- Package skeleton: `murari/__init__.py`, module stubs per the architecture seams
  (`config`, `contract`, `ledger`, `runner`, `session`, `engine`, `cli`).
- `murari/config.py`: env-driven config `MURARI_RUNS` (6), `MURARI_MAX_TURNS` (15),
  `MURARI_MODEL` (`claude-opus-4-8`), `MURARI_HOME` (default `<repo>/.murari`, gitignored);
  minimal no-dependency `.env` loader (kiln pattern — real env vars win; secrets stay in `.env`).
- Make the existing v0.0 tests run under the new wiring (`pytest` from pyproject; `ruff check`
  clean on the new package).

**Dependencies:** None

**Expected result:**
`pytest` and `ruff check` run from the project config; `murari.config` loads budgets and paths
with correct defaults and env overrides.

**Acceptance criteria:**
- [ ] `pytest` discovers and passes the existing v0.0 suite under `pyproject.toml`.
- [ ] `ruff check .` passes on the new package.
- [ ] **Unit test:** config defaults, env overrides, `.env` loading, `MURARI_HOME` default
      `<repo>/.murari` — no network, no paid calls.
- [ ] Ties to roadmap §v0.1 Task "Wire pyproject.toml and config loading".

---

### MUR-007 — Canon v2 install + contract v2 re-pin

**Description:**
Install the role-parameterized canon v2 as the live agent and re-pin the output contract from
v1 to **v2**. Touches: **agent** (+ contract seam). This is the planned v1→v2 seam change: the
spec ([brainstormer.md](../brainstormer.md), [strategies.md](../strategies.md)) already defines
v2; this issue makes code and tests match it.

**What needs to be done:**
- Install `spec/brainstormer.md` (canon v2) verbatim as `.claude/agents/brainstormer.md`,
  replacing the v1 canon proven in v0.0.
- `murari/contract.py`: the v2 schema (`role`, `target_idea`, `mutation_type`, hypotheses with
  `id`/`parents`, `born_from: search|prior|mutation|user`, `next_role`, nullable
  `document_delta`, `dry_run`) + the fence/preamble-tolerant `extract_contract` (promote the
  v0.0 test helper into package code; tests import it from the package).
- Synthetic v2 fixtures: one valid contract per role (6), plus malformed variants (bad role,
  unknown mutation type, missing `id`, `confirmed` without source from a generative role).
- **Re-pin the contract tests to v2**; retire the v1 schema assertions (v0.0 captured fixtures
  stay in-repo as historical v1 artifacts; the extractor tests keep running against them since
  extraction is version-independent).
- **Optional (allowed, by hand, not CI):** one real smoke run with canon v2 to validate the
  synthetic fixtures against reality — reusing the v0.0 exception.

**Dependencies:** MUR-006

**Expected result:**
The live agent is canon v2, and `murari.contract` validates v2 for all six roles with the
extractor shared between engine and tests.

**Acceptance criteria:**
- [ ] `.claude/agents/brainstormer.md` matches `spec/brainstormer.md` (v2, byte-identical).
- [ ] **Contract test:** v2 schema pinned — valid per-role fixtures pass; malformed variants
      fail; generative roles (`generate`/`mutate`) with a `confirmed` verdict are rejected
      (source gate).
- [ ] **Contract test:** `extract_contract` handles bare / fenced / prose-preamble JSON
      (regression from the v0.0 findings).
- [ ] v1 assertions retired deliberately in this issue (seam + test move together); suite green.
- [ ] Ties to roadmap §v0.1 Tasks "Canon v2 + role modules" and "Contract v2 … re-pin".

---

### MUR-008 — LEDGER v2: parser, lineage, journal, per-move dry-run

**Description:**
The orchestrator's read-side of the shared state: parse LEDGER v2 (H-ids, statuses, `parents`
lineage, «випробувано» marks, the run journal, the dry counter) and implement per-move
productivity evaluation. Touches: **orchestrator** (+ workspace-format seam). The agent still
*writes* these files; Python must *read* them to schedule moves and enforce budgets.

**What needs to be done:**
- `murari/ledger.py`: parse `## Гіпотези` entries (`[H2][confirmed] … — джерело: url —
  випробувано: 1`, `parents: H3` / `H3+H5`, `mutation: <type>`), `## Прогони` journal lines
  (move, executor agent/user, produced ids), and the dry counter.
- Lineage helpers: id allocation check (sequential, never reused), parent resolution,
  descendants-of, "strongest verdict" ordering (for `combine` partner and target selection).
- Per-move productivity rules from [strategies.md](../strategies.md) (generate ≥3, evaluate ≥1
  sourced verdict, deepen ≥2 sources, oppose ≥1 counter-argument, mutate ≥1 descendant,
  weave = document rebuilt) → `is_dry(move, before, after)`.
- Synthetic v2 workspace fixtures (ledger with lineage, journal, marks) for tests.

**Dependencies:** MUR-006, MUR-007

**Expected result:**
`murari.ledger` turns a v2 workspace into typed state the engine can schedule from, including
per-move dry-run verdicts.

**Acceptance criteria:**
- [ ] **Contract test:** LEDGER v2 format pinned — ids, statuses, sources, `parents` (1 and 2),
      mutation types, «випробувано», journal lines, dry counter all parse; malformed lines
      surface errors, not silent drops.
- [ ] **Unit test:** lineage helpers (descendants, strongest-verdict ordering) and `is_dry` for
      all six moves against before/after fixtures — mocks only.
- [ ] v0.0 workspace-format tests retired/superseded deliberately alongside (v1 fixtures remain
      as historical artifacts).
- [ ] Ties to roadmap §v0.1 Task "LEDGER v2 … format tests".

---

### MUR-009 — AgentRunner seam: verified invocation, per-role tools, mock

**Description:**
The single place that talks to `claude -p`: the verified `--append-system-prompt` invocation
behind a thin, mockable interface, with per-role tool narrowing and clean failure. Touches:
**orchestrator**. CI never calls the real CLI — `MockAgentRunner` returns canned v2 envelopes.

**What needs to be done:**
- `murari/runner.py`: `AgentRunner` protocol + `ClaudeCliRunner` building the verified command
  (canon body minus frontmatter via `--append-system-prompt`, `--model` from config,
  `--max-turns`, `--output-format json`, `cwd` = session dir) — the v0.0 finding, now as code.
- Per-role `--allowedTools` narrowing per [strategies.md](../strategies.md): Фантазер/Ткач →
  `Read,Write`; Алхімік → `Read,Write` (+`WebSearch` iff `mutation_type == "analogy"`);
  Суддя/Дослідник/Опонент → full quartet; always `--disallowedTools Bash,Task`.
- Kickoff-prompt builder: role module + `target_idea` + `mutation_type` + style step → seed text
  (each role's prompt fragment is a separate, testable unit).
- Envelope handling: parse run JSON via `murari.contract`; on invalid/missing output raise a
  typed error and **leave the workspace untouched** (no partial state written by Python).
- `MockAgentRunner` for tests: canned per-role v2 envelopes + scripted workspace mutations.

**Dependencies:** MUR-006, MUR-007

**Expected result:**
The engine can request "one move of role X on target Y" without knowing anything about the CLI,
and tests can swap in the mock.

**Acceptance criteria:**
- [ ] **Unit test:** command construction per role — tool narrowing matrix (incl. the `analogy`
      exception), model/max-turns from config, canon body without frontmatter.
- [ ] **Unit test:** kickoff-prompt builder per role module (role, target, mutation type
      rendered; no role → full-cycle fallback wording).
- [ ] **Unit test:** invalid/missing JSON → typed error, workspace files untouched.
- [ ] `MockAgentRunner` exercised by the suite (no real `claude` invocation anywhere in CI).
- [ ] Ties to roadmap §v0.1 Task "AgentRunner seam" and the sandbox invariants (tools ⊆ quartet,
      `Bash`/`Task` always disallowed).

---

### MUR-010 — Session lifecycle: create, open-and-continue, graceful failure

**Description:**
Session directories as code: create a fresh timestamped session, reopen an existing one to
continue its document, and keep the workspace safe on failure. Touches: **orchestrator**.
Formalizes what `scripts/new-session.sh` does by hand today.

**What needs to be done:**
- `murari/session.py`: create `MURARI_HOME/brainstorm-sessions/session-<YYYYMMDD-HHMMSS>[-slug]/`
  with `input/TOPIC.md` (written by the caller — later the chat layer) and `output/artifacts/`;
  slugify names; collision-safe.
- Open-and-continue: load an existing session (validate layout, read ledger state via
  `murari.ledger`), so the next move builds on the prior document; the document's `updated`
  stamp advances on the next weave.
- Failure hygiene: a failed/invalid run leaves `output/` exactly as it was (artifacts of the
  failed envelope may be kept under `output/artifacts/` for debugging).
- Session listing helper (for the future `/open` picker; a plain "most recent first" list now).

**Dependencies:** MUR-006

**Expected result:**
`murari.session` creates and reopens sessions with the exact on-disk layout the agent and the
scripts already use.

**Acceptance criteria:**
- [ ] **Unit test:** create — layout (`input/`, `output/artifacts/`), naming (timestamp+slug),
      collision behavior; all under a tmp `MURARI_HOME`.
- [ ] **Unit test:** open-and-continue — reopening a fixture session exposes ledger state and
      the existing document; unknown/malformed dirs raise typed errors.
- [ ] **Unit test:** failure hygiene — after a simulated invalid run, `output/` state files are
      byte-identical to before.
- [ ] Ties to roadmap §v0.1 Task "Session lifecycle" and the DoD clause "reopen an existing
      session to continue its document".

---

### MUR-011 — Style engine + CLI: sequences, randomness, budgets, ownership

**Description:**
The heart of v0.1: execute a **style** — a sequence of role moves — over a session, with
deterministic randomness, per-move budgets, target selection, the DOCUMENT ownership guard, and
a CLI to drive it. Touches: **orchestrator** (+ tests). Integrates MUR-008/009/010.

**What needs to be done:**
- `murari/engine.py`: run a style (`explore`/`debate`/`riff`/`investigate` (default)/`evolve`/
  `premortem`) as its move sequence from [strategies.md](../strategies.md); after each move,
  re-read the workspace (via `murari.ledger`), record per-move dry-run, advance the dry counter.
- Target selection (deterministic rules): `deepen`/`oppose` pick the strongest relevant
  hypothesis; `evolve` mutates only `confirmed`/`partial` survivors; honor an explicit target
  when the style step names one.
- **Deviation hook (rule-based):** two dry moves in a row → swap the next move per the agent's
  `next_role` suggestion or a fallback rule; log the deviation with its justification in the
  engine output.
- **Randomness in the orchestrator:** seeded `random.Random` picks mutation types and `combine`
  partners; the seed is recorded in the run log for reproducibility.
- Budgets: stop at `MURARI_RUNS` moves; pass `MURARI_MAX_TURNS`; refuse to start a move when
  exhausted; per-move budget profiles logged (cheap/medium/expensive).
- **DOCUMENT ownership guard:** snapshot `DOCUMENT.md` before a non-weave move; if it changed,
  fail that move loudly (roadmap v0.4 hardens this further; the engine-level check lands here).
- `murari/cli.py` (`python -m murari`): `new <topic>`, `open <session>`, `run [--style KEY]
  [--moves N] [--seed N]` — the headless driver for the whole DoD.
- **Integration test:** a full `investigate` session against `MockAgentRunner` — six moves,
  ledger grows with ids/lineage/journal, only weave's mock writes DOCUMENT.md, budgets stop the
  engine, deviation triggers on scripted dry moves; a second styled session reopens and
  continues the first.

**Dependencies:** MUR-008, MUR-009, MUR-010

**Expected result:**
From the CLI: create a session, run a full styled session (default `investigate`) move by move
under budgets, reopen and continue it — everything the v0.1 DoD names.

**Acceptance criteria:**
- [ ] **Unit test:** style tables (all six sequences), target selection rules, deviation rule
      (fires after 2 dry, logs justification), seeded mutation/combine picker (same seed → same
      picks), budget stop conditions.
- [ ] **Unit test:** ownership guard — a non-weave move that mutates DOCUMENT.md fails the move.
- [ ] **Integration test:** full styled session on `MockAgentRunner` per the description —
      no paid APIs.
- [ ] CLI drives new/open/run end-to-end on mocks (subprocess-free smoke via entry function).
- [ ] Ties to roadmap §v0.1 DoD: styled session from the CLI, ledger with ids/lineage/journal,
      budgets honored, only weave touches DOCUMENT.md, graceful degradation, open-and-continue.

---

## v0.1 scope notes

**Total effort:** ~3 weeks (S+M+M+M+S+L).
**Critical path:** MUR-006 → MUR-007 → MUR-009 → MUR-011.
**Phase DoD (roadmap §v0.1):** from the CLI you can run a full styled session (default
`investigate`) — the engine executes role moves in sequence, the ledger grows with
ids/lineage/journal, budgets are honored, only weave touches DOCUMENT.md; a session can be
reopened and continued; invalid agent output degrades gracefully without corrupting the
workspace.
**Contracts pinned this phase:** the agent **JSON output v2** (per-role fixtures + source gate,
MUR-007), **LEDGER v2 format** (ids/lineage/journal/dry counter, MUR-008), the **AgentRunner
invocation + per-role tool matrix** (MUR-009), and the **ownership guard** (MUR-011). The v1
pins from v0.0 are retired deliberately in MUR-007/008 as their v2 successors land.
**Model/mock note:** CI mocks the agent (`claude -p`) via `MockAgentRunner` — **no paid APIs**;
one optional real smoke run (by hand, MUR-007) is allowed to validate the v2 fixtures against
reality.
**Companion documents:**
- [roadmap.md](../roadmap.md) — version goals, per-phase Goal/Tasks/DoD/Tests (§v0.1).
- [architecture.md](../architecture.md) — tiers, workspace, contract v2, sandbox invariants, v0.0 findings.
- [strategies.md](../strategies.md) — roles, styles, mutation types, budgets, ownership (accepted 2026-07-05).
- [mission.md](../mission.md) — principles and the Definition of done.
- Generated on upload: `phase1-github-report.md` (MUR-xxx → GitHub #), then `phase1-execution-report.md`.
