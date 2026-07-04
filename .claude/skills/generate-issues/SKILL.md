---
name: generate-issues
description: Decompose a roadmap phase (v0.0–v0.5) into a per-phase GitHub-issues file at spec/implementation/phase{n}-issues.md, ready for /upload-issues.
---

# Skill: Generate Phase Issues

Decompose one roadmap **phase** (`v0.n`) from [spec/roadmap.md](../../../spec/roadmap.md)
into a fine-grained, dependency-ordered **issues file** written to
`spec/implementation/phase{n}-issues.md`. The output is the input to
`/upload-issues` (which pushes it to GitHub) and then `/execute-issues` (which
implements it).

murari is one version — **v0**, the prototype — built core-outward across six
phases `v0.0–v0.5`. This skill only writes the local file; it never touches GitHub.

## Usage

```
/generate-issues <phase>
```

- `/generate-issues 0` — decompose phase **v0.0** → `spec/implementation/phase0-issues.md`
- `/generate-issues v0.2` — phase **v0.2** → `spec/implementation/phase2-issues.md`
- `/generate-issues 4` — phase **v0.4** → `spec/implementation/phase4-issues.md`

One file per **phase** (`v0.n`), matching the `/upload-issues` and `/execute-issues`
convention. IDs (`MUR-xxx`) are **globally sequential** and continue across phase files.

Phase → label → title map (v0 has one version, six phases):

| phase | n | label prefix | title |
|-------|---|--------------|-------|
| v0.0 | 0 | `p0::` | Agent alone (firing the core) |
| v0.1 | 1 | `p1::` | Orchestration (headless) |
| v0.2 | 2 | `p2::` | Chat layer (Haiku) |
| v0.3 | 3 | `p3::` | TUI (Textual) |
| v0.4 | 4 | `p4::` | Sandbox hardening |
| v0.5 | 5 | `p5::` | Acceptance |

## Instructions

### Step 0: Read inputs

1. Normalize the phase to `v0.n` and its number `n` (e.g. `0` → v0.0/n=0,
   `v0.2` → v0.2/n=2). The output filename uses `phase{n}`; the label prefix is `p{n}::`.
2. Read [spec/roadmap.md](../../../spec/roadmap.md) §`v0.n` — the phase's **Goal**,
   short description, **Tasks**, **Definition of Done (DoD)**, and **Tests**. These
   four are the raw material: Tasks → issues, DoD/Tests → acceptance criteria.
3. Read [spec/architecture.md](../../../spec/architecture.md) for the two-head
   architecture and the seams the phase touches, [spec/mission.md](../../../spec/mission.md)
   for the principles and the Definition of done, and — when the phase touches the
   agent — the agent canon [spec/brainstormer.md](../../../spec/brainstormer.md).
   [spec/murari-CONCEPT.md](../../../spec/murari-CONCEPT.md) is the origin concept if
   deeper context is needed.
4. Read `CLAUDE.md` for code conventions, the component map, and the budgets/invariants.
5. **Find the next free `MUR-xxx` id:** scan existing
   `spec/implementation/phase*-issues.md`; continue from the highest id used. If none
   exist yet, start at `MUR-001`. (`spec/implementation/` may not exist yet — create it.)
6. If `spec/implementation/phase{n}-issues.md` already exists, ask whether to overwrite
   or append (continuing the id sequence).

### Step 1: Decompose the phase

Turn the phase's **Tasks** into a small set of issues (typically **3–7**), each a
coherent, independently shippable slice:

- Size each **S** (1–2 d) / **M** (3–5 d) / **L** (5–8 d).
- Order by dependency; the first issue is usually the **gate** (the seam/structure
  everything else builds on).
- Assign each issue an **Area** — the component it touches: `agent`, `chat`, `tui`,
  `orchestrator`, `sandbox`, `tests`, or `spec`. (`/upload-issues` reads this from the
  summary table and turns it into a `p{n}::area:{area}` label.)
- Map each issue to part of the phase Tasks; together they must satisfy the phase
  **DoD** and encode the phase **Tests**.
- **Bake tests into every issue.** CI mocks the agent (`claude -p`), the Haiku chat
  model, and web search — **no paid APIs**. The one exception is **v0.0**, proven by a
  **real by-hand run** (the point of v0.0 is to prove the agent itself); its durable
  artifacts are the seeded contract + workspace-format tests. Every other phase is
  fully mocked: unit for pure logic, contract for any seam, an integration turn where
  relevant.
- A **seam change** carries an `architecture.md` update (and the agent canon at
  `.claude/agents/brainstormer.md` / [spec/brainstormer.md](../../../spec/brainstormer.md)
  if the cycle or output changes) **plus its contract test** in the **same** issue.
  The stable seams:
  - the agent **JSON output** `{hypotheses, fresh_ideas, next_probes, document_delta, dry_run}` (+ the hypothesis status enum `open|confirmed|refuted|partial`),
  - the **workspace file formats** `LEDGER.md` / `SOURCES.md` / `IDEAS.md` / `DOCUMENT.md` (+ the dry-run counter),
  - the **Haiku single-tool boundary** (exactly one tool, `run_brainstorm(seed)`),
  - the **sandbox invariants** (tools = `WebSearch,WebFetch,Read,Write`; `Bash`/`Task` disallowed; Read/Write confined to the session dir; one-level chain; de-identified queries).
- Stay **within the phase** — don't pull later phases' scope in early (the roadmap
  builds core-outward, agent first; cheap-first, simplicity-first).

### Step 2: Write the issues file

Write `spec/implementation/phase{n}-issues.md` using **exactly** this format (the
summary table's columns must match what `/upload-issues` parses — including **Area**):

````markdown
# Phase v0.{n} — GitHub Issues

Issues for phase **v0.{n} — {phase title}** (version **v0 — the prototype**), derived
from the per-phase Goal / Tasks / DoD / Tests in [roadmap.md](../roadmap.md) (§v0.{n})
and the contracts in [architecture.md](../architecture.md). This file is scoped to a
single phase; IDs continue from the previous phase (MUR-{prev} → **MUR-{first}…{last}**).

{1–3 sentences: what the phase does, the seams it extends, why now.}

## Issues Summary Table

| # | ID | Title | Size | Area | Phase | Dependencies |
|---|----|-------|------|------|-------|--------------|
| 1 | MUR-{first} | {title} | M | {area} | p{n} | -- |
| 2 | MUR-{…} | {title} | S | {area} | p{n} | MUR-{first} |
| … | … | … | … | … | … | … |

**Size legend:** S = 1–2 days, M = 3–5 days, L = 5–8 days
**Area:** agent · chat · tui · orchestrator · sandbox · tests · spec

---

## Dependency Tree

```
MUR-{first} ({gate})
  |
  +-- MUR-{…} (…) --+
  |                 |
  +-- MUR-{…} (…) --+
                    |
           MUR-{…} (…)  => {phase DoD}
```

**Parallelization hints:** {which gate first; what runs in parallel after}.

---

## v0.{n} — {phase title}

### MUR-{id} — {Title}

**Description:**
{1–3 sentences. Note which component(s) it touches: agent / orchestrator / chat / tui / sandbox / tests / spec.}

**What needs to be done:**
- {bullet}
- {bullet}

**Dependencies:** {MUR-ids, or None}

**Expected result:**
{one sentence}

**Acceptance criteria:**
- [ ] {functional criterion}
- [ ] **Contract test:** {seam pinned} — *(only if a seam changes)*
- [ ] **Unit test:** {pure logic} against **mocks** (mock agent / Haiku / web search — no paid call)
- [ ] {ties to the phase DoD / Tests in roadmap §v0.{n}}

---

{repeat the `### MUR-{id} …` block per issue}

## v0.{n} scope notes

**Total effort:** {rough estimate}.
**Critical path:** MUR-{…} → … → MUR-{…}.
**Phase DoD (roadmap §v0.{n}):** {restate the DoD}.
**Contracts pinned this phase:** {the seams + their tests}.
**Model/mock note:** CI mocks the agent (`claude -p`), the Haiku chat model, and web
search — **no paid APIs**{, except v0.0's real by-hand run if n = 0}.
**Companion documents:**
- [roadmap.md](../roadmap.md) — version goals, per-phase Goal/Tasks/DoD/Tests (§v0.{n}).
- [architecture.md](../architecture.md) — the two-head architecture, the agent loop, sandbox invariants.
- [mission.md](../mission.md) — principles and the Definition of done.
- Generated on upload: `phase{n}-github-report.md` (MUR-xxx → GitHub #), then `phase{n}-execution-report.md`.
````

### Step 3: Report

Show the user: the file path, the issue count, the `MUR-xxx` id range, and the
critical path. Suggest the next step:

```
/upload-issues @spec/implementation/phase{n}-issues.md
```

(Do **not** create GitHub issues here — that's `/upload-issues`. This skill only writes
the local issues file.)

## Important Rules

- **One file per phase** (`v0.n`) at `spec/implementation/phase{n}-issues.md`.
- **IDs are globally sequential** (`MUR-xxx`), continuing across phase files — never reset per phase.
- **Area on every issue.** The summary table carries an Area column (agent/chat/tui/orchestrator/sandbox/tests/spec) — `/upload-issues` turns it into the `p{n}::area:{area}` label.
- **Tests in every issue.** Acceptance criteria include the unit/contract/integration tests; the agent, Haiku, and web search are mocked — no paid call. The sole exception is v0.0's real by-hand run.
- **Seam = architecture + test together.** Any change to a stable seam (the agent JSON output, the workspace file formats, the Haiku single-tool boundary, the sandbox invariants) lands its `spec/architecture.md` update — and the agent canon if the cycle/output changes — and its contract test in the same issue.
- **Scope to the phase.** Map issues to the phase's Tasks/DoD/Tests; don't pull later phases in early (core-outward, agent first; cheap-first, simplicity-first).
- **Honor the DoD.** The issues together must satisfy the phase DoD and Tests in roadmap §v0.n.
- **Sandbox invariants are hard constraints.** Tools = `WebSearch,WebFetch,Read,Write`; `Bash`/`Task` disallowed; Read/Write confined to the session dir; one-level chain; de-identified queries. Never author an issue that weakens these.
- **Ask on ambiguity.** If the phase's Tasks are unclear or under-specified, ask the user before inventing scope.
- **Don't touch GitHub.** This skill writes only the local file; `/upload-issues` pushes it.
