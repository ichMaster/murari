# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

**v0.0 complete (tag `v0.0.1`), v0.1 not started.** The repo holds the design specs, the proven
agent canon, v0.0's captured fixtures + 12 passing offline tests, and by-hand helper scripts.
Implementation language is **Python**; the full `pyproject.toml` (ruff + pytest wiring) lands in
v0.1 — until then run tests with a bare `python3 -m pytest tests/`.

Source of truth:
- [spec/strategies.md](spec/strategies.md) — **roles & styles (accepted 2026-07-05)**: six roles, six styles, five mutation types, the user as participant, contract v2. Ukrainian.
- [spec/brainstormer.md](spec/brainstormer.md) — the canonical agent definition (role-parameterized canon v2), installed at `.claude/agents/brainstormer.md` (its YAML frontmatter is the agent's frontmatter). Ukrainian.
- [spec/architecture.md](spec/architecture.md) — derived architecture: tiers, workspace, contract, sandbox invariants, v0.0 findings.
- [spec/roadmap.md](spec/roadmap.md) — phases v0.0–v0.5 (roles/styles woven in) + the decision register.
- [spec/mission.md](spec/mission.md) — the problem, values, Definition of done.
- [spec/murari-CONCEPT.md](spec/murari-CONCEPT.md) — the original concept (historical origin; superseded in places by the docs above). Ukrainian.

**Reading the specs:** decision tables mark items `✅ accepted` (locked) or `🔸 tentative`
(changeable). Treat accepted items and the sandbox invariants below as hard constraints.

## Development workflow (SDLC skills)

A GitHub-issues pipeline lives in `.claude/skills/` (ported from the Lumi project). Work is
organized per **roadmap phase** (v0.0–v0.5). Issues are `MUR-xxx` (globally sequential), labels
`p{n}::` map to phase `v0.n`, phase files live under `spec/implementation/`.

- `/generate-issues <phase>` — decompose a roadmap phase into `spec/implementation/phase{n}-issues.md`.
- `/upload-issues <file>` — create the GitHub issues (labels, dependencies, report).
- `/execute-issues <p{n}::phase:{n}>` — implement in dependency order: implement → validate → commit → push → close → report. One issue per commit; never bumps the version automatically.
- `/release-version <A.B.C>` — bump `VERSION`/`RELEASE.txt`, commit, annotated-tag, push.

Semver: phase `v0.n` → `0.n.0`. **v0.0 was released as `0.0.1`** (proof milestone; revised
decision), the orchestrator ships `0.1.0`, graduation is `1.0.0`. CI mocks the agent
(`claude -p`), Haiku, and web search — **no paid APIs in tests** (the deliberate exceptions:
v0.0's by-hand run, and single smoke runs where the roadmap allows them). Billing split:
**Opus only ever via `claude -p` (MAX subscription), never the API key; Haiku via the metered
Messages API** (key in gitignored `.env`).

## What murari is

**murari** is a brainstorming tool where the human is a **participant, not a spectator**. A user
drives a chat/TUI over topics; behind the chat, headless Claude Code runs play **six brainstorm
roles** — Фантазер (`generate`, wild ideas), Суддя (`evaluate`, verdicts with sources), Дослідник
(`deepen`, deep-dive into one idea), Опонент (`oppose`, counter-arguments — **no winner**),
Алхімік (`mutate`, "what if…" in 5 types), Ткач (`weave`, sole writer of `DOCUMENT.md`) — **one
move per run**, sequenced by **styles** (`investigate` is the default; also
explore/debate/riff/evolve/premortem). The Haiku chat layer (**Ведучий**) detects which role the
user is playing and covers the rest with agent moves. The session deliverable is a
**timestamped** working document (`DOCUMENT.md`) that remains on disk after exit. Sessions are
**resumable**, but there is no *implicit* cross-session memory: a fresh `/b` starts blank.

The name (Sanskrit मुरारि, "enemy of Mura") fits a system whose job is to cut down weak hypotheses.

## Architecture — two heads, six roles

```
user ──TUI──> Ведучий (haiku) ──spawn──> claude -p (one role move)
               ^                               |
               |        session workspace      |
               +--  input/TOPIC.md             |
                    output/LEDGER.md (+журнал)-+
                    output/SOURCES.md IDEAS.md
                    output/DOCUMENT.md  <- deliverable (written ONLY by weave)
```

- **Chat layer / Ведучий** — Python + Claude Haiku (HTTP API). Conversation, topic framing,
  seeds — plus facilitation: detects the user's current role, closes the remaining roles
  (complementarity; adversarial pairing only in `debate`, no winner declared), selects the style.
  Haiku has **exactly one tool**: `run_brainstorm(seed, role, target_idea?, mutation_type?, style_step?)`.
  No filesystem, no Bash, no web of its own.
- **TUI** — Textual, three panels: chat; ledger (statuses, lineage, run journal); document
  (read-only to the user in v0). Status bar: style / role / runs remaining. Async, non-blocking.
- **Agent** — Claude Code headless (`claude -p`, canon via `--append-system-prompt`). Model
  **Opus 4.8**. One run = one role move. Tools at most `WebSearch, WebFetch, Read, Write`,
  **narrowed per role** (Фантазер/Ткач without web; Алхімік web only for `analogy`).
- **Session workspace** — `MURARI_HOME/brainstorm-sessions/session-<timestamp>[-slug]/` with
  `input/TOPIC.md` (chat-written, RO to agent) and `output/` (`LEDGER.md`, `SOURCES.md`,
  `IDEAS.md`, `DOCUMENT.md`, `artifacts/run-N.{json,log}`). The workspace files are the agent's
  only memory between runs (fresh context each run).

## The agent loop (one run = one move)

A run executes **one move of one role**, passed in the seed by the orchestrator (`role`,
`target_idea` H-id, `mutation_type`); with no role given (by-hand run) the agent falls back to
the full investigate cycle `read → diverge → select → verify → synthesize → document → write`.
The key edge is the **reverse** one: verify findings seed the next divergence — freshness comes
from search, not priors.

Dry-run accounting is **per-move**: generate ≥3 candidates; evaluate ≥1 sourced verdict; deepen
≥2 sources; oppose ≥1 counter-argument; mutate ≥1 descendant; weave = document rebuilt. Two dry
runs in a row → the agent proposes a new angle/role.

The last message of every run is **only** the contract JSON — **v2** (see
[spec/strategies.md](spec/strategies.md)): `role`, `target_idea`, `mutation_type`, hypotheses
with `id`/`parents`, `born_from: search|prior|mutation|user`, `next_role`, nullable
`document_delta`, `dry_run`. **Note:** the tests currently pin **contract v1** (no role/id
fields) from the v0.0 captured run; v0.1 re-pins them to v2. Statuses: `open`, `confirmed`,
`refuted`, `partial`. **No verdict without a source URL.** Generative moves (generate/mutate/user
input) produce only `open` candidates; only evaluating moves (evaluate/deepen/oppose) attach
verdicts; only `weave` writes `DOCUMENT.md`.

## Sandboxing & isolation — hard invariants

- **Two privilege tiers.** Tier 1 (Ведучий/Haiku): exactly one tool, `run_brainstorm(…)`.
  Tier 2 (agent): at most `WebSearch, WebFetch, Read, Write` narrowed per role; Read/Write
  confined to the session workspace — no `../`, no absolute paths, no escaping symlinks.
  Bash is disallowed.
- **Exactly one level of delegation.** Roles never call each other; the deterministic
  orchestrator sequences moves (`murari → role → result`, depth always 1). `Task`/nested agents
  disallowed.
- **File ownership.** Only `weave` writes `DOCUMENT.md`; the user doesn't edit it directly in v0.
- **Agent output is data, not instructions.** The chat layer treats run output (and fetched web
  content) as quoted material, never as commands.
- **No personal data leaves.** Only topic and hypothesis content go into search queries.

The verified invocation (v0.0 finding: `--agents brainstormer` does **not** run as the agent
when `Task` is disabled — the canon must ride `--append-system-prompt`):

```
claude -p "<kickoff: role, target, mutation_type>" \
  --append-system-prompt "$(<canon body, frontmatter stripped>)" \
  --model claude-opus-4-8 \
  --allowedTools <role's tool set> \
  --disallowedTools Bash,Task \
  --max-turns N --output-format json
```

run with `cwd` = the session workspace; the policy is also duplicated in the workspace's
`.claude/settings.json`. Two more v0.0 findings: the JSON arrives ` ```json `-fenced and
sometimes after a prose preamble (parser must locate the block), and the envelope's
`web_search_requests` counter is unreliable (trust sourced URLs in LEDGER/SOURCES).

## Config (budgets)

Opus 4.8 is expensive — these caps are the primary cost ceiling per session. `MURARI_RUNS`
counts moves; per-move budget profiles (generate/mutate/weave cheap, evaluate/oppose medium,
deepen expensive). User moves are free.

| var | meaning | default |
|---|---|---|
| `MURARI_RUNS` | agent moves per session | 6 |
| `MURARI_MAX_TURNS` | `--max-turns` per move | 15 |
| `MURARI_RUN_TIMEOUT` | seconds before a single move is killed | 900 (15 min) |
| `MURARI_MODEL` | agent model | opus (claude-opus-4-8) |
| `MURARI_HOME` | base sessions dir | `<repo>/.murari` (gitignored) |

## Running & testing today (v0.0 artifacts)

- `scripts/new-session.sh [name]` — create a session (`input/TOPIC.md` from `examples/TOPIC.md`).
- `scripts/brainstorm.sh <session-dir> [max-turns]` — one by-hand agent run (honors
  `MURARI_MODEL`); stats + tokens/cost land in `output/artifacts/run-N.log`. See
  [docs/USAGE.md](docs/USAGE.md).
- `python3 -m pytest tests/` — 12 offline tests: contract v1 + workspace formats, seeded from
  the captured real run in `tests/fixtures/captured-run/`. No paid calls.

## Interface commands (planned)

`/b <topic>` (fresh session) · `/open <session>` (continue) · `/style <key>`
(explore/debate/riff/investigate/evolve/premortem) · `/go` (force next move) · `/ledger`
(state incl. lineage/journal) · `/quit` (exit; session dir remains).

## Conventions

- **Language.** Specs' canon + product content (chat, `DOCUMENT.md`, `LEDGER.md`, agent output)
  are **Ukrainian**; search queries in whatever finds the best results (usually English); code
  identifiers, role/style keys, and this file in English.
- **Document is state, not a log.** `DOCUMENT.md` is rebuilt by `weave`; history lives in
  `LEDGER.md` (H-ids, lineage, run journal).
- **Randomness lives in the orchestrator** (mutation types, combine partners) — never ask the
  model to "pick randomly".
