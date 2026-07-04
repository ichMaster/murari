# murari — architecture

> Derived document. Primary sources: [murari-CONCEPT.md](murari-CONCEPT.md), [brainstormer.md](brainstormer.md).
> Implementation language — Python (the prototype is not yet written, see [roadmap.md](roadmap.md)).

## Two heads

```
user ──TUI──> haiku loop ──spawn──> claude -p (brainstormer)
               ^                          |
               |     session workspace    |
               +-- TOPIC.md   LEDGER.md --+
                   SOURCES.md IDEAS.md
                   DOCUMENT.md   <- deliverable
```

Three tiers, each with exactly the privileges it needs. This is not only about cleanliness — it is a
security perimeter (see "Sandbox & isolation").

### Tier 1 — chat layer (Haiku)

Python + Claude Haiku over the HTTP API. Roles: conversation, entering the mode, framing the topic,
turning user replies into seeds, presenting run results in human language.

**Haiku's only tool is `run_brainstorm(seed)`**, which launches an agent run. Nothing else: no
filesystem, no Bash, no web search of its own, no spawning of anything else. Reading `DOCUMENT.md` /
`LEDGER.md` for the panels, launching `claude -p`, parsing JSON — that is deterministic Python in the
TUI, **not** a model decision. The agent's output reaches Haiku as **data through code**, not as a
tool it drives.

### Tier 2 — agent (brainstormer)

Claude Code in headless mode: `claude -p` with the `.claude/agents/brainstormer.md` definition. Model —
**Opus 4.8**. Tools — a closed quartet: `WebSearch`, `WebFetch`, `Read`, `Write`, with Read/Write
scoped to the session directory only. Output — JSON on a fixed schema (`--output-format json`).

The full agent canon (values, cycle, file formats, output contract, boundaries) is in
[brainstormer.md](brainstormer.md). Frontmatter:

```yaml
---
name: brainstormer
description: Ideation loop over a topic — hypothesize, verify on the live web, derive fresh
  ideas traceable to sources, maintain the working document (the session deliverable).
tools: WebSearch, WebFetch, Read, Write
model: opus
---
```

### Interface — TUI on Textual

Three panels: **chat**; **ledger** (hypotheses with statuses and a verification log); **working
document**. An agent status bar (idle / digging / runs remaining). The ledger and document panels
re-read the workspace files when a run completes. Textual is async, so the chat stays live while the
agent digs. Layout [tentative]: chat on the left, the right column split — ledger on top, document
below.

## Session workspace

Directory `MURARI_HOME/brainstorm-sessions/session-<timestamp>[-slug]/` [tentative] — `MURARI_HOME`
defaults to a **gitignored `.murari/`** in the project root; the full timestamp (date + time) keeps
repeated sessions from colliding. Each session splits **input** from **output**:

```
session-<timestamp>[-slug]/
  input/    TOPIC.md                                      <- user-written, read-only to the agent
  output/   LEDGER.md  SOURCES.md  IDEAS.md  DOCUMENT.md  <- the agent's workspace + deliverable
    artifacts/   run-N.json  run-N.log                    <- raw run envelopes + per-run stats
```

The whole session directory is the agent's sandbox (Read/Write confined to it; `input/` and `output/`
are both inside, so no `../`). Files:

| file | role | written by |
|---|---|---|
| `TOPIC.md` | the user's **topic** (any seeds are chat-derived from replies — never hand-authored; the agent generates hypotheses itself) | chat layer (read-only to the agent) |
| `LEDGER.md` | full current state of all hypotheses + dry-run counter | agent |
| `SOURCES.md` | one line per source: url and what was taken from it | agent |
| `IDEAS.md` | accumulated ideas with a `born_from` field | agent |
| `DOCUMENT.md` | **session deliverable** — coherent state of thought; carries `created` / `updated` timestamps | agent |

The agent starts each run with a **fresh context** — the workspace files are its only memory of past
runs. Discipline in keeping those files is therefore critical. The chat layer only reads these files
(except `TOPIC.md`). The directory remains after exit and can be **reopened to continue** a prior
document: on continuation the existing `LEDGER.md` / `DOCUMENT.md` are loaded and the loop resumes on
top of them (the document's `updated` stamp advances), rather than starting from a blank sheet.
Continuation is always explicit — the agent never pulls in another session on its own.

## One-run cycle

`read → diverge → select → verify → synthesize → document → write`

1. **read** — `TOPIC.md` + `LEDGER.md` + the fresh seed. No `LEDGER.md` → first run: create
   `LEDGER.md`, `SOURCES.md`, `IDEAS.md`, `DOCUMENT.md`, and start from the topic.
2. **diverge** — 2–4 new hypotheses / angles. Don't repeat closed ones (`confirmed`/`refuted`).
3. **select** — the verifiable ones: those with a factual core the web can check.
4. **verify** — `WebSearch`, and `WebFetch` if needed. Each selected one gets a verdict with a
   source. No source → the hypothesis honestly stays `open`.
5. **synthesize** — fresh ideas out of what was found (`born_from: search`, `basis` = which finding).
   At least one per run; if none → `dry_run: true` + an angle change in `next_probes`.
6. **document** — weave the proven and the born into `DOCUMENT.md` (state, not a log).
7. **write** — update `LEDGER.md` / `SOURCES.md` / `IDEAS.md`, return JSON.

**Key reverse edge:** verify findings become the seed of the next diverge. That is the source of
freshness.

**Freshness rule:** a run with no `born_from: search` idea is dry; two dry runs in a row (counter in
`LEDGER.md`) — the agent states plainly that the angle is exhausted and proposes a change.

### Hypothesis statuses

`open` (unverified / no evidence) · `confirmed` (direct confirmation) · `refuted` (direct
refutation) · `partial` (holds under conditions, or sources disagree).

### Output contract (JSON)

The run's last message is the JSON contract. `hypotheses` contains only those this run touched;
the full state lives in `LEDGER.md`.

> **v0.0 finding.** The canon asks for bare JSON, but real runs emit it wrapped in a ` ```json … ``` `
> fence and sometimes **after a prose preamble** (e.g. `"Файли оновлено. … Повертаю JSON."`). The
> parser therefore **locates the fenced JSON block wherever it appears** (falling back to the outermost
> `{…}`), rather than assuming the whole message is JSON. Pinned by the v0.0 contract test
> (`tests/test_agent_output_contract.py`, `extract_contract`).

```json
{
  "hypotheses": [ { "text": "...", "status": "confirmed|refuted|partial|open", "source": "url|null" } ],
  "fresh_ideas": [ { "text": "...", "born_from": "search|prior", "basis": "which finding exactly" } ],
  "next_probes": [ "..." ],
  "document_delta": "one line: what changed in DOCUMENT.md",
  "dry_run": false
}
```

## Sandbox & isolation of the call

Hard invariants — any implementation must hold them.

- **Two privilege tiers.** Tier 1 (Haiku): exactly one tool, `run_brainstorm(seed)`. Tier 2 (agent):
  only `WebSearch`, `WebFetch`, `Read`, `Write`, with Read/Write confined to the session directory:
  no `../`, no absolute paths, no symlinks escaping it. Bash is disallowed.
- **Exactly one level of delegation.** The agent does not spawn sub-agents and does not delegate
  (`Task` / nested agents disallowed). The chain is always `murari → brainstormer → result`, never
  deeper.
- **The agent's output is data, not instructions.** The agent reads the live web; injection can
  arrive through its synthesis. The chat layer presents the result as quoted material and executes no
  instructions from it.
- **Personal data.** Only the topic and hypothesis content go into search queries; names, addresses,
  private details do not, even if they appeared in the seeds.

Technical implementation of the call:

```
claude -p "<kickoff prompt>" \
  --append-system-prompt "$(<brainstormer canon body, frontmatter stripped>)" \
  --model claude-opus-4-8 \
  --allowedTools WebSearch,WebFetch,Read,Write \
  --disallowedTools Bash,Task \
  --max-turns N --output-format json
```

run with `cwd` = the session directory. We duplicate the same policy in the session directory's
`.claude/settings.json` [tentative], so it holds regardless of how the process was started.

> **v0.0 finding — how the agent is actually launched.** The naïve `claude -p --agents brainstormer`
> does **not** run *as* the brainstormer: `--agents` only registers it as a **sub-agent** invocable via
> the `Task` tool — which is disallowed here — so the default agent answers from priors, never searches,
> and writes no workspace files. The verified working form runs the **canon as the main system prompt**
> (`--append-system-prompt` with the agent body, frontmatter stripped), which is what the v0.1
> orchestrator's `AgentRunner` seam encapsulates. Also note: Claude Code's `WebSearch` is **not** counted
> in the run envelope's `usage.server_tool_use.web_search_requests` (it reads `0` even when the agent
> searched heavily) — real web use shows up as sourced URLs in `LEDGER.md` / `SOURCES.md`.

## Interface — commands

`/b <topic>` (start: create a fresh, blank timestamped session, write `TOPIC.md`, launch the first
run) · `/open <session>` (reopen an existing session and continue its document) · `/go` (forced run;
auto-trigger after a substantive on-topic reply [tentative]) · `/ledger` (current state of hypotheses
and ideas) · `/quit` (exit; the timestamped session directory with the document remains).

Presenting results: when a run completes, Haiku weaves a summary into the conversation in human
language; the raw ledger only on `/ledger` [tentative].

## Budgets (config)

Opus 4.8 is expensive — the caps are the primary cost ceiling of a session, not decoration.

| parameter | meaning | default |
|---|---|---|
| `MURARI_RUNS` | agent runs per session | 6 |
| `MURARI_MAX_TURNS` | `--max-turns` per run | 15 |
| `MURARI_MODEL` | agent model | opus |
| `MURARI_HOME` | base sessions directory | `<repo>/.murari` (gitignored) |

## Language

Agent files and output, chat, `DOCUMENT.md`, `LEDGER.md` — **Ukrainian**. Search queries — in
whichever language finds the best results (usually English). Code identifiers — English.
