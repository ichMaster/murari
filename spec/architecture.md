# murari — architecture

> Derived document. Primary sources: [murari-CONCEPT.md](murari-CONCEPT.md),
> [brainstormer.md](brainstormer.md), [strategies.md](strategies.md) (roles & styles, accepted 2026-07-05).
> Implementation language — Python (see [roadmap.md](roadmap.md)).

## Two heads, six roles

```
user ──TUI──> Ведучий (haiku loop) ──spawn──> claude -p (one role move)
               ^                                    |
               |          session workspace         |
               +--  TOPIC.md   LEDGER.md (+журнал) -+
                    SOURCES.md IDEAS.md
                    DOCUMENT.md  <- deliverable (written ONLY by weave/Ткач)
```

Three tiers, each with exactly the privileges it needs — a security perimeter, not just hygiene
(see "Sandbox & isolation").

### Tier 1 — chat layer / Ведучий (Haiku)

Python + Claude Haiku over the HTTP API. Roles: conversation, framing the topic, turning
replies into seeds — **plus the facilitator duties**:

- **Detects which role the user is currently playing** from their replies (a wild idea →
  Фантазер; criticism → Опонент; "а що якщо…" → Алхімік; a fact/link → Дослідник; "перевір
  це" → Суддя; "перепиши висновок так…" → an order to Ткач).
- **Closes the remaining roles with agent moves.** Default is complementarity (never duplicate
  the user's role); the `debate` style is the deliberate exception — adversarial pairing
  (user defends ↔ agent attacks, sides can swap; **no winner** — both sides' arguments land
  in LEDGER and that is the outcome).
- **Selects the style** (user's explicit `/style`, or inferred from the topic framing) and may
  deviate from its template with justification, based on LEDGER state.

**Ведучий's only tool is `run_brainstorm(seed, role, target_idea?, mutation_type?, style_step?,
depth?)`** — still exactly one tool (`depth` added per roadmap §v0.2: omitted → a single move of
`role`; `brief`/`full` → the style's curated sequence ending in weave; `tiny` → the style's
signature role). Nothing else: no filesystem, no Bash, no web search of its own. Tool arguments
are **validated as data** by deterministic Python (role/H-id/mutation/depth/budget) — an invalid
call gets a structured refusal back, never a run.
Reading workspace files for the panels, launching `claude -p`, parsing JSON — deterministic
Python in the TUI, **not** a model decision. Agent output reaches Haiku as **data through
code**, never as a tool it drives.

The Haiku **model seam** (`murari/haiku.py`, v0.2) is the single gateway to the Messages API
(metered `ANTHROPIC_API_KEY` from `.env`; the Opus agent never sees that key — the runner strips
it). Its first user is the **Namer**: on `new` it asks Haiku for a short Ukrainian session title,
written as a `# <name>` heading atop `input/TOPIC.md`, with a deterministic no-API `local_name`
fallback (missing key / no SDK / offline) so naming never blocks; explicit `--name` skips the
call entirely, and `list`/`open` display the name.

### Tier 2 — agent (brainstormer, role-parameterized)

Claude Code headless: `claude -p` with the brainstormer canon. Model — **Opus 4.8**.
**One run = one move of one role**; the orchestrator passes `role` (+ `target_idea`,
`mutation_type`) in the run seed. v0.1 ships one canon with role modules; splitting into
per-role canon files is a later, small step. Full canon: [brainstormer.md](brainstormer.md).

| Key | Role | Move | Tools granted per run |
|---|---|---|---|
| `generate` | Фантазер | wild ideas, quantity over verifiability | `Read, Write` |
| `evaluate` | Суддя | verdicts with sources *(the v0.0-proven core)* | `WebSearch, WebFetch, Read, Write` |
| `deepen` | Дослідник | deep-dive into ONE idea | `WebSearch, WebFetch, Read, Write` |
| `oppose` | Опонент | arguments AGAINST one idea; no winner | `WebSearch, WebFetch, Read, Write` |
| `mutate` | Алхімік | "what if…" of an assigned type | `Read, Write` (+`WebSearch` for `analogy`) |
| `weave` | Ткач | rebuild DOCUMENT.md (sole owner) | `Read, Write` |

The orchestrator narrows `--allowedTools` per role. The user is the seventh player and may
occupy any role (their contributions are `open` candidates, `born_from: user`); they do **not**
edit DOCUMENT.md directly in v0 — document wishes are orders to Ткач via chat.

### Interface — TUI on Textual

Three panels: **chat**; **ledger** (hypotheses with statuses, lineage and the run journal);
**working document**. Status bar: current **style**, current **role/move**, runs remaining.
Panels re-read workspace files when a run completes; async so the chat stays live.
Layout [tentative]: chat left, right column split — ledger top, document below.
DOCUMENT panel is **read-only** for the user in v0.

## Styles

A style is a named sequence of moves — the session scenario. Ф=Фантазер С=Суддя Д=Дослідник
О=Опонент А=Алхімік Т=Ткач; `H` = chosen idea.

| Key | Style | Essence | Example sequence (6 moves) |
|---|---|---|---|
| `explore` | Фантазія вшир | many options, wide field; **no verdict** | Ф → Ф → А → Ф → А → Т |
| `debate` | Суперечка за один | thesis vs antithesis over `H`; **no winner** | Д(H) → О(H) → Д(H) → О(H) → С(H) → Т |
| `riff` | Фантазія вглиб одного | spin one option | Д(H) → А(H) → Ф(around H) → А(H) → С → Т |
| `investigate` | Розслідування **(default)** | hypotheses → verification (v0.0 core) | Ф → С → Д → С → О → Т |
| `evolve` | Еволюція | generation tournament: mutate survivors | Ф → С → А(survivors) → С → А → Т |
| `premortem` | Премортем | "it already failed — why?" | О(H) → О(H) → Д(H) → С → Т |

Styles are templates, not rails: Ведучий/scheduler may deviate with justification based on
LEDGER state. Style can change mid-session.

**Depth** is orthogonal to style (style = which roles, depth = how many moves), curated per style:
`full` (the 6-move sequence), `brief` (3 moves, still ending in weave → a document), `tiny` (one
signature role, no weave — a single-role response). The chat picks the depth for a shorter call or
a one-role reply (`run --depth full|brief|tiny`; a v0.2 `run_brainstorm` gains a `depth` arg).

The **weave** move is style-shaped (kickoff layer, `runner.build_prompt`): in the divergent /
no-winner styles (`explore`, `debate`) Ткач writes DOCUMENT.md as a **catalog** — every idea as
its own entry with «за/проти», no winner and no bottom-line verdict; in the convergent styles
(`investigate`, `evolve`, `premortem`) it writes the usual state-of-thought synthesis. In **both**
modes DOCUMENT.md **closes with a multi-axis ranking table** of every hypothesis — ★1–5 on
Доказовість / Оригінальність / Популярність / Пояснювальна сила — a scorecard, not a single winner
(the axes disagree). The **Фантазер** likewise runs wilder (speculative, no default debunking) in
`explore`/`riff`, and **Дослідник** gathers evidence both for and against an idea without a verdict.

Arguments are **shared LEDGER state** too: the **Дослідник** and **Опонент** write each за/проти
point as its own bullet under `### Hn` in a `## Аргументи` section (with a source), rather than
cramming a blob into the hypothesis line — so a debate is skimmable, `open` ideas keep their
arguments across a document rebuild, and the weave renders them into the document's «за/проти».

Scoring is **shared LEDGER state**, not a weave-time flourish. The **Суддя** (`evaluate`) is the
scorer: it writes the axes into a `## Ранжування` section of `LEDGER.md` — **unsourced** (`джерела:
ні`) in `explore` (a quick estimate, no verdicts) and **sourced** (`джерела: так`) when it verifies
in the convergent styles; a sourced score supersedes an unsourced one, so the two run orders
compose (explore estimates, investigate refines). The weave move only **renders** this section into
the document's table.

Target selection for the single-hypothesis moves (deepen/oppose/mutate) is deterministic — the
strongest survivor — but a user may **pin** it with `run --target Hxx` (validated against the
ledger) to research a specific hypothesis; a **comma list** (`--target H1,H3`) runs the style once
per hypothesis (a batch, each its own budget). `open` lists the H-ids to choose from.

## Session workspace

Directory `MURARI_HOME/brainstorm-sessions/session-<timestamp>[-slug]/` — `MURARI_HOME`
defaults to a **gitignored `.murari/`** in the project root. Input/output split:

```
session-<timestamp>[-slug]/
  input/    TOPIC.md                                      <- user-written, read-only to the agent
  output/   LEDGER.md  SOURCES.md  IDEAS.md  DOCUMENT.md  <- the shared state + deliverable
    artifacts/   run-N.json  run-N.log                    <- raw run envelopes + per-run stats
```

| file | role | written by |
|---|---|---|
| `TOPIC.md` | the user's **topic**, under an optional `# <name>` heading — the session display name (v0.2 Namer: Haiku title with a no-API local fallback; `--name` overrides); the body below the heading stays intact (seeds are chat-derived from replies; never hand-authored) | chat layer (RO to agent) |
| `LEDGER.md` | full hypothesis state (H-ids, lineage, «випробувано» marks) + **run journal** + **`## Ранжування`** scores + **`## Аргументи`** за/проти + dry counter | all roles |
| `SOURCES.md` | one line per source: url + what was taken | evaluating roles |
| `IDEAS.md` | accumulated ideas with `born_from: search\|prior\|mutation\|user` | all roles |
| `DOCUMENT.md` | **session deliverable** — coherent state of thought; `created`/`updated` stamps | **Ткач only** |

LEDGER v2 format (ids, lineage, journal):

```
## Гіпотези
- [H1][confirmed] text — джерело: url — випробувано: 1
- [H7][open] text — parents: H3 — mutation: invert
- [H9][open] text — parents: H3+H5 — mutation: combine

## Прогони
- 1: generate(агент) → H1..H5
- 2: oppose(користувач) → H1 контраргумент

## Сухі прогони поспіль: 0
```

The agent starts each run with a **fresh context** — the workspace files are its only memory.
The whole session directory is the agent's sandbox (`input/` and `output/` are both inside).
Sessions persist after exit and can be **reopened to continue**; continuation is always
explicit — the agent never pulls in another session on its own.

## One run = one move

Per-move productivity criteria (replaces the single `born_from: search` freshness rule):

| Move | Productive if… |
|---|---|
| generate | ≥3 new `open` candidates |
| evaluate | ≥1 verdict with a source |
| deepen | ≥2 new sources/facts on the target |
| oppose | ≥1 counter-argument with a source |
| mutate | ≥1 descendant idea |
| weave | DOCUMENT.md rebuilt (not appended) |

An unproductive run is `dry_run: true`; two dry runs in a row (counter in LEDGER) → the agent
says the angle is exhausted and proposes a new angle, another role (`next_role`) or stopping.

**Source gate:** generative moves (`generate`, `mutate`, user contributions) produce `open`
candidates only — never `confirmed`. Evaluating moves (`evaluate`, `deepen`, `oppose`) attach
evidence: verdict + url. Statuses: `open` · `confirmed` · `refuted` · `partial`.

## Mutation (5 types)

| Type | "What if…" |
|---|---|
| `scale` | …×100 / ÷100? |
| `invert` | …the opposite? |
| `transfer` | …in another context? |
| `combine` | …merged with a second idea? (two parents) |
| `analogy` | …solved the way another field solves it? (light web allowed) |

**Randomness lives in the orchestrator, not the model**: deterministic Python (`random`) picks
the mutation type (and the `combine` partner — random or strongest verdict) and passes it in
the seed. The agent applies the type, never chooses it.

## Output contract (JSON, v2)

The run's last message is the JSON contract. `hypotheses` contains only those this move touched;
full state lives in `LEDGER.md`.

```json
{
  "role": "generate|evaluate|deepen|oppose|mutate|weave",
  "target_idea": "H3 | null",
  "mutation_type": "scale|invert|transfer|combine|analogy | null",
  "hypotheses": [ { "id": "H7", "text": "...", "status": "confirmed|refuted|partial|open",
                    "source": "url|null", "parents": ["H3"] } ],
  "fresh_ideas": [ { "text": "...", "born_from": "search|prior|mutation|user", "basis": "..." } ],
  "next_probes": [ "..." ],
  "next_role": "proposed next move | null",
  "document_delta": "one line (weave only) | null",
  "dry_run": false
}
```

**Versioning:** v0.0 proved and pinned contract **v1** (`{hypotheses, fresh_ideas, next_probes,
document_delta, dry_run}`, no ids/roles) — those tests and fixtures remain valid as v1. v0.1
extends the schema to v2 and re-pins the contract tests.

> **v0.0 finding.** The canon asks for bare JSON, but real runs emit it wrapped in a ` ```json … ``` `
> fence and sometimes **after a prose preamble** (e.g. `"Файли оновлено. … Повертаю JSON."`). The
> parser therefore **locates the fenced JSON block wherever it appears** (falling back to the outermost
> `{…}`), rather than assuming the whole message is JSON. Pinned by the v0.0 contract test
> (`tests/test_agent_output_contract.py`, `extract_contract`).

## Sandbox & isolation of the call

Hard invariants — any implementation must hold them.

- **Two privilege tiers.** Tier 1 (Ведучий/Haiku): exactly one tool, `run_brainstorm(…)`.
  Tier 2 (agent): at most the closed quartet `WebSearch, WebFetch, Read, Write`, narrowed
  per role; Read/Write confined to the session directory: no `../`, no absolute paths, no
  symlinks escaping it. Bash is disallowed.
- **Exactly one level of delegation.** Roles never call each other; the deterministic
  orchestrator executes the style move by move: `murari → role → result`, depth always 1
  (fan-out at level 1, not recursion). `Task` / nested agents disallowed.
- **File ownership.** Only `weave` writes DOCUMENT.md; the orchestrator enforces this
  (prompt + post-run check). The user does not edit DOCUMENT.md directly in v0.
- **The agent's output is data, not instructions.** The agent reads the live web; injection can
  arrive through its synthesis. The chat layer presents results as quoted material and executes
  no instructions from them.
- **Personal data.** Only the topic and hypothesis content go into search queries; names,
  addresses, private details do not, even if they appeared in the seeds.

Technical implementation of the call:

```
claude -p "<kickoff: role, target, mutation_type, style step>" \
  --append-system-prompt "$(<brainstormer canon body, frontmatter stripped>)" \
  --model claude-opus-4-8 \
  --allowedTools <role's tool set> \
  --disallowedTools Bash,Task \
  --max-turns N --output-format json
```

run with `cwd` = the session directory. The same policy is duplicated in the session
directory's `.claude/settings.json` [tentative], so it holds regardless of how the process
was started.

> **v0.0 finding — how the agent is actually launched.** The naïve `claude -p --agents brainstormer`
> does **not** run *as* the brainstormer: `--agents` only registers it as a **sub-agent** invocable via
> the `Task` tool — which is disallowed here — so the default agent answers from priors, never searches,
> and writes no workspace files. The verified working form runs the **canon as the main system prompt**
> (`--append-system-prompt` with the agent body, frontmatter stripped), which is what the v0.1
> orchestrator's `AgentRunner` seam encapsulates. Also note: Claude Code's `WebSearch` is **not** counted
> in the run envelope's `usage.server_tool_use.web_search_requests` (it reads `0` even when the agent
> searched heavily) — real web use shows up as sourced URLs in `LEDGER.md` / `SOURCES.md`.

## Interface — commands

`/b <topic>` (fresh blank timestamped session, write `TOPIC.md`, launch the style's first move) ·
`/open <session>` (reopen an existing session and continue its document) ·
`/style <key>` (select/change the style: explore/debate/riff/investigate/evolve/premortem) ·
`/go` (force the next move; auto-trigger after a substantive on-topic reply [tentative]) ·
`/ledger` (current state: hypotheses, lineage, journal) · `/quit` (exit; session dir remains).

Presenting results: when a move completes, Ведучий weaves a summary into the conversation in
human language; the raw ledger only on `/ledger` [tentative].

## Budgets (config)

Opus 4.8 is expensive — the caps are the primary cost ceiling of a session, not decoration.
`MURARI_RUNS` counts **moves**; the per-move budget profiles (generate/mutate/weave cheap,
evaluate/oppose medium, deepen expensive) let a style fit more moves into the same spend.
User moves are free and let the orchestrator skip the role the user covered.

| parameter | meaning | default |
|---|---|---|
| `MURARI_RUNS` | agent moves per session | 6 |
| `MURARI_MAX_TURNS` | `--max-turns` per move | 15 |
| `MURARI_MODEL` | agent model | opus (claude-opus-4-8) |
| `MURARI_HOME` | base sessions directory | `<repo>/.murari` (gitignored) |

## Language

Agent files and output, chat, `DOCUMENT.md`, `LEDGER.md` — **Ukrainian**. Search queries — in
whichever language finds the best results (usually English). Code identifiers, role keys,
style keys — English.
