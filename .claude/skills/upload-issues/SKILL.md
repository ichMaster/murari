---
name: upload-issues
description: Upload issues from a phase issues file to GitHub one by one with proper labels and dependencies.
---

# Skill: Upload Phase Issues to GitHub

Upload issues from a phase issues file to GitHub one by one, with proper labels (prefixed by phase) and dependencies.

## Usage

```
/upload-issues <phase-issues-file>
```

Example: `/upload-issues @spec/implementation/phase0-issues.md`

A phase issues file is the fine-grained breakdown of a roadmap phase (v0.0–v0.5): each phase in [spec/roadmap.md](../../../spec/roadmap.md) is split into one or more `MUR-xxx` issues. Phases are labeled `v0.B`; the skill's `p{n}` maps to `v0.n` (so `p0` = phase v0.0, the agent alone). If the file does not exist yet, derive it from the phase (its Goal / bullets / exit criterion) first, then run this skill.

## Instructions

### Step 1: Read the phase issues file

Read the provided file (e.g., `spec/implementation/phase{n}-issues.md`).

Determine from the file:
- **Phase number** (n): from the filename or heading (e.g., `phase0-issues.md` -> n = `0`, i.e. v0.0)
- **Label prefix**: `p{n}::` (e.g., `p1::`)

Parse the **Issues Summary Table** to extract for each issue:
- `ID` (e.g., MUR-001)
- `Title`
- `Size` (S, M, L)
- `Area` (the component: `agent`, `chat`, `tui`, `orchestrator`, `sandbox`, `tests`, `spec`)
- `Phase` (the roadmap phase it implements, e.g. `p1`)
- `Dependencies` (list of MUR-xxx IDs)

Then parse each **detailed issue section** (heading with MUR-xxx) to extract:
- `Description`
- `What needs to be done` (full content)
- `Dependencies`
- `Expected result`
- `Acceptance criteria` (checklist — should align with the phase exit criterion in roadmap.md and the Definition of done in [spec/mission.md](../../../spec/mission.md))

### Step 2: Confirm with user

Show the user a summary of what will be created:
- Number of issues
- Label prefix (e.g., `p1::`)
- Full list of labels that will be created
- Ask for confirmation before proceeding

### Step 3: Create labels (if they don't exist)

All labels MUST be prefixed with `p{n}::` (phase number).

Label format: `p{n}::{category}:{value}`

Use `gh` to create these labels if they don't already exist (phase titles: p0 — Agent alone (firing the core); p1 — Orchestration; p2 — Chat layer; p3 — TUI; p4 — Sandbox hardening; p5 — Acceptance):

```bash
# Phase label
gh label create "p0::phase:0" --color "0E8A16" --description "Phase v0.0 — Agent alone" 2>/dev/null || true

# Size labels
gh label create "p0::size:S" --color "28A745" --description "Small (1-2 days)" 2>/dev/null || true
gh label create "p0::size:M" --color "FFC107" --description "Medium (3-5 days)" 2>/dev/null || true
gh label create "p0::size:L" --color "DC3545" --description "Large (5-8 days)" 2>/dev/null || true

# Area labels (one per component touched in this phase)
gh label create "p0::area:agent"        --color "6F42C1" 2>/dev/null || true
gh label create "p0::area:orchestrator" --color "1D76DB" 2>/dev/null || true
gh label create "p0::area:chat"         --color "0E8A16" 2>/dev/null || true
# ... tui / sandbox / tests / spec as needed
```

### Step 4: Create issues ONE BY ONE

**IMPORTANT:** Issues must be created one at a time, sequentially. After creating each issue:
1. Show the user the result (issue number, URL)
2. Proceed to the next issue immediately (do not wait for confirmation between issues)

For each issue (in order from the summary table):

1. Build the issue body in markdown:

```markdown
## Description
{description from the detailed section}

## What needs to be done
{full content from the detailed section}

## Dependencies
{dependency list, with references to already-created issue numbers}

## Expected result
{expected result from the detailed section}

## Acceptance criteria
{checklist from the detailed section}

---
**ID:** {MUR-xxx}
**Size:** {S/M/L}
**Phase:** p{n}
**Area:** {agent/chat/tui/orchestrator/sandbox/tests/spec}
```

2. Create the issue with a single `gh issue create` command (one issue per command, never batch):

```bash
gh issue create \
  --title "MUR-xxx: {title}" \
  --label "p0::phase:0,p0::size:{S/M/L},p0::area:{area}" \
  --body "$(cat <<'BODY'
{issue body}
BODY
)"
```

3. Record the mapping: MUR-xxx -> GitHub issue #number

4. Report to user: `Created MUR-xxx -> #{number}: {title}`

5. If the issue has dependencies on already-created issues, add a comment:

```bash
gh issue comment {issue-number} --body "Blocked by #{dep-issue-number} (MUR-xxx)"
```

6. Move to the next issue.

### Step 5: Generate report

After all issues are created, generate a report file at:
`spec/implementation/phase{n}-github-report.md`

Content:

```markdown
# Phase p{n} -- GitHub Issues Report

**Uploaded:** {date}
**Repository:** {github repo URL}
**Total issues:** {count}

## Issue Mapping

| MUR ID | GitHub # | Title | Phase | Labels | URL |
|--------|----------|-------|-------|--------|-----|
| MUR-001 | #5 | Install brainstormer agent | p0 | p0::phase:0, p0::size:S, p0::area:agent | {url} |
| ... | ... | ... | ... | ... | ... |

## Labels Created

- p{n}::phase:{n}
- p{n}::size:S, p{n}::size:M, p{n}::size:L
- p{n}::area:{list}
```

### Step 6: Report to user

Show the user:
- Total issues created
- Link to the GitHub issues page
- Path to the generated report file

## Error Handling

- If `gh` is not authenticated, tell the user to run `gh auth login`
- If the repo has no GitHub remote yet, tell the user to create one (`gh repo create`) before uploading
- If an issue already exists with the same title, skip it and note in the report
- If label creation fails, continue (labels may already exist)
- On any failure, report what was created so far and what remains
