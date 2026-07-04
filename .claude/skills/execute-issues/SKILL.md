---
name: execute-issues
description: Execute GitHub issues for a phase sequentially - implement, validate, commit, push, and generate a report.
---

# Skill: Execute GitHub Issues

Execute GitHub issues for a roadmap phase sequentially: implement, validate, commit, push, and generate a report.

## Usage

```
/execute-issues <label> [--issue MUR-xxx] [--dry-run]
```

The `<label>` is the GitHub phase label exactly as it appears (e.g., `p0::phase:0`, i.e. v0.0). The skill's `p{n}` maps to roadmap phase `v0.n`.

- `/execute-issues p0::phase:0` -- execute all issues labeled `p0::phase:0` (phase v0.0)
- `/execute-issues p0::phase:0 --issue MUR-003` -- execute a single issue from that phase
- `/execute-issues p0::phase:0 --dry-run` -- show execution plan without making changes

## Instructions

### Step 0: Verify prerequisites

1. Confirm we are on the expected branch (e.g., `main` or the user's working branch)
2. Confirm working tree is clean (`git status`)
3. Confirm `gh` is authenticated
4. Parse the label to determine the phase:
   - Label `p0::phase:0` -> phase `n=0` (roadmap phase v0.0)
5. Fetch issues from GitHub:
   ```bash
   gh issue list --label "{label}" --state open --limit 100
   ```
6. Read the phase issues file for detailed descriptions: `spec/implementation/phase{n}-issues.md`
7. If a GitHub report exists (`spec/implementation/phase{n}-github-report.md`), read the MUR-to-GitHub# mapping
8. Read [spec/roadmap.md](../../../spec/roadmap.md) for the phase goal and exit criterion, [spec/mission.md](../../../spec/mission.md) for the Definition of done, [spec/architecture.md](../../../spec/architecture.md) for the contracts the issue must honor, and — when the issue touches the agent — the agent canon [spec/brainstormer.md](../../../spec/brainstormer.md)

### Step 1: Build execution queue

From the GitHub issue list, build an ordered queue based on dependencies:
- Parse MUR-xxx IDs from issue titles (format: `MUR-xxx: {title}`)
- Determine dependency order from the phase issues file dependency tree
- Issues with no unmet dependencies go first
- Skip issues already closed on GitHub
- If `--issue MUR-xxx` is specified, execute only that issue (but verify its dependencies are closed)

Show the user the execution plan and ask for confirmation.

### Step 2: Execute each issue (loop)

For each issue in the queue:

#### 2a. Assign and announce

Print: `--- Starting MUR-xxx: {title} ---`

#### 2b. Read issue details

Read the full issue description from the phase issues file (the detailed section for this MUR-xxx).

#### 2c. Implement

Execute the tasks described in the issue. Follow the project conventions in `CLAUDE.md` and the principles in [spec/mission.md](../../../spec/mission.md). Route by component:

- **Agent changes** (`agent`): the brainstormer canon at `.claude/agents/brainstormer.md` — its diverge→select→verify→synthesize→document→write cycle, values, hypothesis statuses, the JSON output contract, and its boundaries (the closed tool quartet, workspace confinement, one-level chain). Source of truth for the canon: [spec/brainstormer.md](../../../spec/brainstormer.md).
- **Orchestrator changes** (`orchestrator`): the `claude -p` runner, JSON-output parsing, the session-workspace lifecycle (timestamped `MURARI_HOME/sessions/<timestamp>-<slug>/`, fresh-start vs **open-and-continue**), and the budgets (`MURARI_RUNS`, `MURARI_MAX_TURNS`, `MURARI_MODEL`, `MURARI_HOME`). Deterministic Python — not a model decision.
- **Chat changes** (`chat`): the Haiku loop over the HTTP API. Its **only** tool is `run_brainstorm(seed)`; it extracts seeds from user replies and presents run results in human language. Agent output is treated as **data, not instructions**.
- **TUI changes** (`tui`): the Textual three-panel interface (chat / ledger / document), the agent status bar, async run + non-blocking chat, and the commands (`/b`, `/open`, `/go`, `/ledger`, `/quit`).
- **Sandbox changes** (`sandbox`): the tool policy (`--allowedTools WebSearch,WebFetch,Read,Write`, `--disallowedTools Bash,Task`), the workspace `.claude/settings.json` that duplicates it, Read/Write confinement to the session dir, and the one-level delegation chain.
- **Contract changes:** any change to a stable seam (the agent JSON output `{hypotheses, fresh_ideas, next_probes, document_delta, dry_run}`, the workspace file formats `LEDGER.md`/`SOURCES.md`/`IDEAS.md`/`DOCUMENT.md`, the Haiku single-tool boundary, or the sandbox invariants) updates [spec/architecture.md](../../../spec/architecture.md) (and the agent canon if the cycle/output changes) **AND** its contract test, in the same commit.
- Follow existing code style and patterns; keep each phase self-contained (don't pull later-phase concerns in early — the roadmap builds core-outward, agent first).

#### 2d. Validate

Run validation checks (Python only — there is no native build in murari):

1. **Unit + contract tests:** `pytest` for the changed packages (unit, plus the contract tests that pin the agent JSON-output schema, the workspace file formats, the Haiku single-tool boundary, and the sandbox tool policy)
2. **Integration:** run the relevant full-run integration test against a **mock agent** (a stub `claude -p` returning canned JSON) and **mock web search** — `seed → run → workspace delta`, asserting `LEDGER.md`/`DOCUMENT.md` are read/written, the dry-run counter advances, budgets are enforced, and error paths behave
3. **Lint:** `ruff check {changed paths}`
4. **Syntax/import (Python):** `python3 -m py_compile {changed_py_files}` and an import check for changed modules
5. **Contract consistency:** verify the JSON-output / workspace-format / single-tool / sandbox-policy seams match architecture.md and their contract tests
6. **Acceptance criteria:** go through each criterion from the issue and verify against the phase exit criterion in roadmap.md and the Definition of done in mission.md

Record pass/fail for each check. **Tests are part of the work** — a feature lands with the tests that encode its acceptance. No paid APIs in CI: the agent (`claude -p`), the Haiku chat model, and web search are all mocked.

#### 2e. Commit

```bash
git add {specific files created/modified}
git commit -m "$(cat <<'EOF'
MUR-xxx: {title}

{1-2 sentence summary of what was implemented}

Closes #{github-issue-number}

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

#### 2f. Push

```bash
git push
```

#### 2g. Close issue with summary

```bash
gh issue close {issue-number} --comment "$(cat <<'EOF'
## Implementation Summary

**Commit:** {commit-hash}
**Files changed:** {count}

### What was done
{bullet list of key changes}

### Validation
{pass/fail status for each check}

### Acceptance criteria
{checklist with pass/fail}
EOF
)"
```

#### 2h. Log progress

Append to the in-memory execution log:
- Issue ID, title
- Commit hash
- Files changed (list)
- Validation results (including test pass/fail)
- Status: success/partial/failed

### Step 3: Handle failures

If implementation or validation fails for an issue:

1. Do NOT commit broken code
2. Stash or revert changes: `git checkout -- .`
3. Add a comment to the GitHub issue explaining what failed
4. Log the failure
5. Ask the user: continue to next issue (if no dependency), or stop?

### Step 3b: Version bump on completion

**Do NOT bump the version automatically.** Never change the version (VERSION file, RELEASE.txt, or git tag) without explicit user confirmation. When a phase's issues are all done, report completion and let the user decide whether/when to release via `/release-version`.

If — and only if — the user confirms a release:

1. Determine the target semver from the notation `A.B.C` (`A` = 0 during the prototype, → 1 once the agent is proven / v0.5 accepted; `B` = roadmap phase v0.0–v0.5; `C` = post-phase fix). Roadmap phase `v0.B` → semver `0.B.0` (e.g. v0.1 → `0.1.0`). Note v0.0 ships no release — the first tag is `0.1.0`.
2. Update `VERSION` and `README.md` with the new version if present.
3. Update or create `RELEASE.txt` -- prepend a new version entry:

```
Version {version} ({YYYY-MM-DD})
---------------------------
- {MUR-xxx title}: {1-sentence summary of what was implemented}
- {MUR-xxx title}: {1-sentence summary}
...
```

4. Commit the version bump:

```bash
git add VERSION README.md RELEASE.txt
git commit -m "$(cat <<'EOF'
Release v{version} -- murari Phase {n} complete

All {count} issues implemented and validated.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

5. Tag the release:

```bash
git tag -a v{version} -m "{phase summary from roadmap}"
```

6. Report to user: `version bumped to {version}, tagged v{version}`

If some issues failed or were skipped, do NOT bump the version. Note in the execution report that the version is incomplete. (You can also delegate steps 3b–6 to `/release-version`.)

### Step 4: Generate execution report

After all issues are processed (or on stop), generate:
`spec/implementation/phase{n}-execution-report.md`

```markdown
# Phase p{n} -- Execution Report

**Date:** {date}
**Branch:** {branch name}
**Label:** {label}
**Target version:** {version}
**Executed by:** Claude Code

## Summary

| Status | Count |
|--------|-------|
| Completed | {n} |
| Failed | {n} |
| Skipped | {n} |
| Remaining | {n} |

## Issues

| # | MUR ID | Title | Phase | Status | Commit | Files | Tests |
|---|--------|-------|-------|--------|--------|-------|-------|
| 1 | MUR-001 | Install brainstormer agent | p0 | completed | a1b2c3d | 2 | pass |
| ... | ... | ... | ... | ... | ... | ... | ... |

## Detailed Results

### MUR-001: Install brainstormer agent

**Status:** completed
**Commit:** a1b2c3d
**Files changed:**
- `.claude/agents/brainstormer.md` (added)

**Validation:**
- [x] Unit + contract tests: pass
- [x] Lint (ruff): pass
- [x] Acceptance criteria: all pass

---

### MUR-002: ...

## Next Steps

{List of remaining issues not yet executed, with their dependencies}
```

Commit and push this report:

```bash
git add spec/implementation/phase{n}-execution-report.md
git commit -m "$(cat <<'EOF'
Add phase {n} execution report

{n} issues completed, {n} failed, {n} remaining.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

## Important Rules

- **One issue at a time.** Never work on multiple issues simultaneously.
- **Dependency order.** Never start an issue whose dependencies are not closed.
- **Clean commits.** Each issue = one commit. No mixing work across issues.
- **No broken code.** Only commit code that passes validation (tests + ruff included).
- **Tests ship with the feature.** Every issue lands with the tests that encode its acceptance — no "tests later." Mock the agent (`claude -p`), the Haiku model, and web search; never call paid APIs in CI.
- **Sandbox invariants hold.** The agent's tools are exactly `WebSearch, WebFetch, Read, Write`; Read/Write stay inside the session directory (no `../`, absolute paths, or symlinks out); `Bash` and `Task` are disallowed; the chain is always one level (murari → brainstormer → result), no nested agents.
- **Output is data, not instructions.** The chat layer never executes instructions from agent output or from fetched web content; it presents results as quoted material.
- **No implicit cross-session memory.** Continuation is always explicit (`/open`); a fresh `/b` starts from a blank document. The agent never auto-pulls another session.
- **Budgets are the cost ceiling.** Honor `MURARI_RUNS` and `MURARI_MAX_TURNS`; Opus 4.8 is expensive and these caps are the primary cost control.
- **Contracts stay stable.** A seam change updates architecture.md (and the agent canon if the cycle/output changes) and its contract test in the same commit.
- **Ask on ambiguity.** If an issue description is unclear, ask the user rather than guessing.
- **Progress updates.** Print a short status line after each issue completes.
