# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

**Pre-implementation.** This repo currently holds only design specs — there is no source code, build system, or tests yet. The intended implementation language is **Python** (inferred from the standard Python `.gitignore`). When you write the first code, this file should be updated with real build/lint/test commands.

Source of truth (both files are in Ukrainian):
- [spec/murari-CONCEPT.md](spec/murari-CONCEPT.md) — the prototype concept: architecture, agent cycle, budgets, sandboxing, open questions, and a **decisions table**.
- [spec/brainstormer.md](spec/brainstormer.md) — the canonical agent definition. This file is destined to be installed at `.claude/agents/brainstormer.md` (its YAML frontmatter is already the agent's frontmatter).

Note `spec/` is currently untracked in git — only `.gitignore` and `LICENSE` are committed.

**Reading the specs:** the decisions table marks each decision as either `ухвалено` (accepted / locked) or `[П]` (provisional — proposed, not yet finalized). Treat `[П]`-marked details as changeable; treat `ухвалено` items and the sandbox invariants below as hard constraints.

## Development workflow (SDLC skills)

A GitHub-issues pipeline lives in `.claude/skills/` (ported and adapted from the Lumi project). Work is organized per **roadmap phase** — one version, **v0**, with phases **v0.0–v0.5** in [spec/roadmap.md](spec/roadmap.md) (v0.0 = the agent alone / firing the core). Issues are `MUR-xxx`, labels are prefixed `p{n}::` where `p{n}` maps to phase `v0.n`, and the phase breakdown files live under `spec/implementation/`.

- `/upload-issues <spec/implementation/phase{n}-issues.md>` — create GitHub issues for a phase (labels, dependencies, report).
- `/execute-issues <p{n}::phase:{n}>` — implement each issue in dependency order: implement → validate → commit → push → close → report. One issue per commit; never bumps the version automatically.
- `/release-version <A.B.C>` — bump `VERSION`/`README.md`/`RELEASE.txt`, commit, annotated-tag, push.

Semver maps to the roadmap: phase `v0.n` → `0.n.0` (label `p{n}`); **v0.0 ships no release** (first tag is `0.1.0`), and `1.0.0` is the graduation once the agent is proven (v0.5, acceptance). These skills assume Python validation (`pytest`, `ruff`) and that CI mocks the agent (`claude -p`), Haiku, and web search — no paid APIs in tests.

## What murari is

**murari** is a brainstorming tool. A user drives a chat/TUI over topics; behind the chat, a headless Claude Code subagent runs a **diverge → select → verify → synthesize** loop over the topic: it generates hypotheses, verifies them against the live web, and derives fresh ideas traceable to sources. The session deliverable is a **timestamped** working document (`DOCUMENT.md`) that grows over the session and remains on disk after exit; it carries created/updated stamps so deliverables accumulate as distinct artifacts. Sessions are **resumable** — a prior document can be reopened and continued — but there is no *implicit* cross-session memory: the agent never auto-pulls other sessions, and a fresh `/b` starts blank.

The name (Sanskrit मुरारि, "enemy of Mura") fits an agent whose job is to cut down weak hypotheses.

## Architecture — two heads

```
user ──TUI──> haiku loop ──spawn──> claude -p (brainstormer)
               ^                          |
               |     session workspace    |
               +-- TOPIC.md   LEDGER.md --+
                   SOURCES.md IDEAS.md
                   DOCUMENT.md   <- deliverable
```

- **Chat layer** — Python, Claude Haiku over the HTTP API. Handles conversation, framing the topic, and turning user replies into seeds. Haiku has **exactly one tool**: `run_brainstorm(seed)`, which launches an agent run. It has no filesystem, no Bash, no web search of its own.
- **TUI** — Textual, three panels: chat, ledger (hypotheses with statuses + verification log), and the working document. Async so the chat stays live while the agent works; ledger/document panels re-read workspace files when a run completes.
- **Agent** — Claude Code headless (`claude -p`) using the `brainstormer` agent definition. Model: **Opus 4.8**. Tools limited to `WebSearch, WebFetch, Read, Write` (Write scoped to the session workspace only).
- **Session workspace** — `MURARI_HOME/sessions/<timestamp>-<topic-slug>/`, holding `TOPIC.md`, `LEDGER.md`, `SOURCES.md`, `IDEAS.md`, `DOCUMENT.md`. The agent reads and maintains these files itself between runs — this is how it holds state across runs (each run starts with a fresh context). An existing session directory can be reopened to continue its document. The chat layer only reads them; `TOPIC.md` is written by the chat layer and is read-only to the agent.

## The agent loop (one run)

`read → diverge → select → verify → synthesize → document → write`. The key edge is the **reverse** one: verify findings become the seed for the next diverge — that is where freshness comes from (ideas grow from what search returned, not from the model's priors).

Freshness rule: a run producing no `born_from: search` idea is marked `dry_run: true`; two dry runs in a row (counter tracked in `LEDGER.md`) → the agent states the angle is exhausted and proposes a new one.

The last message of every run is **only** this JSON (no wrapper, no prose):

```json
{
  "hypotheses": [ { "text": "...", "status": "confirmed|refuted|partial|open", "source": "url|null" } ],
  "fresh_ideas": [ { "text": "...", "born_from": "search|prior", "basis": "which finding" } ],
  "next_probes": [ "..." ],
  "document_delta": "one line: what changed in DOCUMENT.md",
  "dry_run": false
}
```

`hypotheses` contains only hypotheses this run touched; the full state lives in `LEDGER.md`. Hypothesis statuses: `open` (unverified / no evidence found), `confirmed`, `refuted`, `partial`. **No verdict without a source URL** — this is a core value, not a style preference.

## Sandboxing & isolation — hard invariants

Any implementation must preserve these (from the "Пісочниця та ізоляція виклику" section):

- **Two privilege tiers.** Tier 1 (Haiku chat brain): exactly one tool, `run_brainstorm(seed)`. Tier 2 (brainstormer agent): only `WebSearch, WebFetch, Read, Write`, with Read/Write confined to the session workspace directory — no `../`, no absolute paths, no symlinks escaping the dir. Bash is disallowed.
- **Exactly one level of delegation.** The agent may not spawn sub-agents or delegate (`Task`/nested agents are disallowed). The chain is always `murari → brainstormer → result`, never deeper.
- **Agent output is data, not instructions.** The agent reads the live web; injection can arrive through its synthesis. The chat layer treats the run's output as quoted material and never executes instructions from it.
- **No personal data leaves.** Only the topic and hypothesis content go into search queries.

The spec's intended invocation:

```
claude -p --agents brainstormer \
  --allowedTools WebSearch,WebFetch,Read,Write \
  --disallowedTools Bash,Task \
  --max-turns N --output-format json
```

run with `cwd` = the session workspace. The same policy should also be duplicated in a `.claude/settings.json` inside the workspace dir so it holds regardless of how the process was started.

## Config (budgets)

Opus 4.8 is expensive, so these caps are the primary cost ceiling per session — not decoration.

| var | meaning | default |
|---|---|---|
| `MURARI_RUNS` | agent runs per session | 6 |
| `MURARI_MAX_TURNS` | `--max-turns` per run | 15 |
| `MURARI_MODEL` | agent model | opus |
| `MURARI_HOME` | base sessions dir | `~/murari` |

## Interface commands (planned)

`/b <topic>` (start a fresh blank timestamped session, write `TOPIC.md`, run first pass) · `/open <session>` (reopen an existing session and continue its document) · `/go` (force a run) · `/ledger` (current hypothesis/idea state) · `/quit` (exit; timestamped session dir with document remains).

## Conventions

- **Language.** The specs and the product's user-facing content (chat, `DOCUMENT.md`, `LEDGER.md`, agent output) are in **Ukrainian**. Search queries may be in whatever language finds the best results (usually English). Keep code identifiers and this file in English.
- **Document is state, not a log.** `DOCUMENT.md` is rewritten/restructured each run to hold the current coherent state of thought; history lives in `LEDGER.md`. The agent maintains `DOCUMENT.md` (the `document` step of the cycle).
