# murari — How to use

> **Scope.** Two ways to run murari today:
> - **v0.1 — the `murari` CLI (recommended):** a headless Python orchestrator that runs a whole
>   **style** (a sequence of role moves) over a session — it drives `claude -p` for you, reads the
>   ledger between moves, picks targets, enforces budgets, and guards the document.
> - **v0.0 — the agent, by hand:** the lower-level path — one agent run at a time via a shell
>   script. Still valid; it's what the CLI automates.
>
> No chat and no TUI yet (those are v0.2/v0.3 — see [roadmap.md](../spec/roadmap.md)).

---

## v0.1 — the `murari` CLI

### Install

```bash
cd /path/to/murari
pip install -e .          # registers the `murari` command
#   …or skip install and use:  python -m murari <args>
```

You also need the **Claude Code CLI** (`claude`) logged in to a plan that can run Opus (a Claude
**MAX** subscription is enough — the agent runs on your subscription, not the metered API), and
the brainstormer canon installed at `.claude/agents/brainstormer.md` (it ships in the repo).

> **Cost.** `murari new` / `murari run` spawn **real Opus 4.8 runs** — one per move. The budgets
> below (`MURARI_RUNS`, `MURARI_MAX_TURNS`) are the primary cost ceiling. A failed run restores
> the workspace to exactly its pre-run state, so a crash never leaves half-written files.

### Quick start (TL;DR)

```bash
# create a session AND run the default style over it in one command
murari new "теплові насоси для багатоквартирних будинків" --name heat

# …read the deliverable
open .murari/brainstorm-sessions/session-*-heat/output/DOCUMENT.md

# later: continue the same session with a different style
murari run .murari/brainstorm-sessions/session-*-heat --style evolve
```

### Commands

| Command | What it does |
|---|---|
| `murari new "<тема>" [--name S] [--style K] [--moves N] [--seed J]` | Create a fresh session (writes `input/TOPIC.md`, auto-named — see below) **and** run one style over it. |
| `murari run <session-dir> [--style K] [--moves N] [--seed J]` | Run one style over an **existing** session (open-and-continue — the ledger grows, it isn't reset). |
| `murari open <session-dir>` | Print a session's current state (name, topic, ledger summary, whether a document exists) **without running**. |
| `murari list` | List all sessions, most recent first, each with its name. |
| `murari chat [<session-dir>] [--new "<тема>"] [--name S] [--style K] [--depth D]` | With no args: reopens the most recent session (or starts an empty one). **Facilitated chat (v0.2)** over a session — the headless stand-in for the v0.3 TUI. Every reply first passes a Haiku **router**: a document question / summary ask / plain talk is answered by another Haiku call grounded in DOCUMENT.md; a brainstorm ask records your contribution (free, `born_from: user`) and launches the Claude agent for **one move** of the routed role — the router can launch nothing deeper. Deep runs are yours: `/go [стиль] [глибина]` over the session topic. Commands: `/style [key]` · `/go [стиль] [глибина]` · `/ledger` · `/quit` (the session dir remains). |

**Session naming.** On `new`, Haiku (`MURARI_CHAT_MODEL`, metered `ANTHROPIC_API_KEY` from
`.env`) titles the session in Ukrainian and writes the name as a `# <name>` heading atop
`input/TOPIC.md`; with no key / no `anthropic` SDK / offline, a local fallback derives the name
from the topic — naming never blocks and costs nothing in that case. An explicit `--name` is used
as-is (no Haiku call). `list` and `open` show the name.

**Options**

- `--style` — one of the six styles below (default **`investigate`**).
- `--depth` — how many moves: **`full`** (the 6-move sequence, default), **`brief`** (3 moves,
  still ends in a document), **`tiny`** (a single signature role, no document). See the depth
  table under **Styles**.
- `--moves N` — cap the run at `N` moves (never above `MURARI_RUNS`).
- `--seed J` — the RNG seed for mutation types and `combine` partners; the **same seed replays the
  same choices** (randomness lives in the orchestrator, never the model). Default `0`.
- `--target Hxx` — (`run` only) pin the single-hypothesis moves (deepen/oppose/mutate) to a chosen
  hypothesis instead of the auto-picked strongest. Use `open` to see the H-ids. A **comma list**
  (`--target H1,H3`) runs the whole style **once per hypothesis** (each its own budget). All ids
  are validated up front — an unknown one errors before anything runs.
- `--name S` — an optional slug for the session folder (`new` only; ASCII, else timestamp-only).

### Examples per command

**`new`** — start a fresh topic and run a style over it (the common entry point):

```bash
# create a session and run the default style (investigate)
murari new "чому міста засипані шаром глини"

# name the folder, pick a style, and fix the seed for a reproducible run
murari new "теплові насоси для багатоквартирних будинків" --name heat --style explore --seed 7

# cheap smoke: cap to 2 moves to sanity-check the pipeline before spending a full run
murari new "тема" --moves 2
```

**`run`** — continue an *existing* session (open-and-continue; the ledger grows, never resets):

```bash
# add more thinking to a session with a different style
murari run .murari/brainstorm-sessions/session-20260705-2312-heat --style evolve

# a glob works when the slug is unique; same seed → same mutation/partner picks
murari run .murari/brainstorm-sessions/session-*-heat --seed 7

# debate a *specific* hypothesis (see its H-id via `murari open`) — no winner is declared
murari run .murari/brainstorm-sessions/session-*-heat --style debate --target H3

# debate several, one run each (H1, then H3, then H5)
murari run .murari/brainstorm-sessions/session-*-heat --style debate --target H1,H3,H5

# stretch a session under a tighter budget
MURARI_RUNS=3 murari run .murari/brainstorm-sessions/session-*-heat --style debate
```

**`open`** — peek at a session's state without running anything (free — no Opus call):

```bash
murari open .murari/brainstorm-sessions/session-20260705-2312-heat
# session: /…/session-20260705-2312-heat
# topic: теплові насоси для багатоквартирних будинків
# ledger: 5 hypotheses, 3 survivors, dry-streak 0
#   H1 [confirmed] теплові насоси окупаються за ~7 років …  ★ дк5 ор2 пп4 пс4 (джерела)
#   H2 [partial] шумність — головний бар'єр …               ★ дк3 ор3 пп2 пс3 (чорнова)
#   …
# document: present
```

The listed H-ids are what you pass to `run --target Hxx`.

**`list`** — find your sessions, newest first (the folder timestamp sorts chronologically):

```bash
murari list
# session-20260705-2312-heat
# session-20260704-2312-clay
```

A typical loop: `new` (start a topic) → `open` / `list` (check state) → `run <dir> --style evolve`
(continue the same topic with another style) → read `output/DOCUMENT.md`.

### Styles

A style is a named **sequence of moves** — the session scenario. Every style ends in `weave` (the
only move that writes `DOCUMENT.md`). Roles: Ф=Фантазер · С=Суддя · Д=Дослідник · О=Опонент ·
А=Алхімік · Т=Ткач; `H` = the chosen strongest idea.

| Key | Style | Essence | Works on | Sequence |
|---|---|---|---|---|
| `explore` | Фантазія вшир | many options, unsourced scoring — **no verdict** | all ideas | Ф → Ф → А → Ф → С → Т |
| `debate` | Суперечка за один | thesis vs antithesis over `H` — **no winner** | **one chosen `H`** (`--target`) | Д → О → Д → О → С → Т |
| `riff` | Фантазія вглиб одного | spin one option | **one chosen `H`** (`--target`) | Д → А → Ф → А → С → Т |
| `investigate` | Розслідування **(default)** | hypotheses → verification (the v0.0 core) | all ideas | Ф → С → Д → С → О → Т |
| `evolve` | Еволюція | mutate the survivors | survivors (`confirmed`/`partial`) | Ф → С → А → С → А → Т |
| `premortem` | Премортем | "it already failed — why?" | **one chosen `H`** (`--target`) | О → О → Д → С → Т |

**Works on** = which hypotheses the style's core moves act on. `explore`/`investigate` sweep the
**whole pool**; `evolve` mutates the **survivors** (verdict `confirmed`/`partial`); `debate`,
`riff` and `premortem` revolve around **one** hypothesis — the strongest by default, or the one you
pin with `run --target Hxx`.

Styles are templates, not rails: after **two dry moves in a row** the engine deviates — to the
agent's suggested `next_role`, or a fallback (mutate the survivors, else generate) — and logs the
deviation with its justification.

**Depth** (`--depth`) is orthogonal to style — the style says *which* roles, the depth *how many*
moves. Curated per style:

| Style | `full` (default) | `brief` | `tiny` |
|---|---|---|---|
| investigate | Ф → С → Д → С → О → Т | Ф → С → Т | С |
| explore | Ф → Ф → А → Ф → С → Т | Ф → А → Т | Ф |
| debate | Д → О → Д → О → С → Т | Д → О → Т | О |
| riff | Д → А → Ф → А → С → Т | Д → А → Т | А |
| evolve | Ф → С → А → С → А → Т | С → А → Т | А |
| premortem | О → О → Д → С → Т | О → Д → Т | О |

`brief` always ends in `weave`, so you still get a document; `tiny` is a **single role** (no
weave) — a one-role response (its output lands in the ledger). Example: `run <dir> --style debate
--depth tiny --target H2` = just the Опонент's counter-arguments on H2.

The move behaviour is **style-shaped**: in the divergent / no-winner styles (`explore`, `debate`)
the Ткач writes `DOCUMENT.md` as a **catalogue** — every idea with its «за/проти», no winner and
no bottom-line verdict — while the convergent styles (`investigate`, `evolve`, `premortem`) get a
state-of-thought synthesis. The Фантазер runs wilder in `explore`/`riff`, and the Дослідник
gathers evidence **both for and against** an idea (without issuing a verdict).

Scoring is **shared LEDGER state**: the **Суддя** rates every hypothesis ★1–5 on four axes —
**Доказовість · Оригінальність · Популярність · Пояснювальна сила** — into a `## Ранжування`
section of `LEDGER.md`. `explore` scores **without sources** (a quick estimate); `investigate`
verifies and **re-scores with sources** (a sourced score supersedes an unsourced one), so the two
run orders compose. Every `DOCUMENT.md` **ends with a ranking table** rendered from that section —
a scorecard, not a single winner (the axes deliberately disagree). `murari open` shows the current
scores next to each hypothesis (`★ дк5 ор2 пп4 пс4 (джерела)` / `(чорнова)`).

### What a run prints

Moves are **streamed live** — each of the N steps prints as it starts and finishes (so you see
which step of 6 the agent is on while the run is still going), then a summary:

```
created /…/.murari/brainstorm-sessions/session-20260705-2312-heat
стиль investigate: 6 ходів
[1/6] generate — виконую…
[1/6] generate — готово за 41s (продуктивний) · in 39.0k out 340 $0.58
[2/6] evaluate — виконую…
[2/6] evaluate — готово за 88s (продуктивний) · in 41.2k out 610 $0.71
[3/6] deepen →H1 — виконую…
…
[6/6] weave — готово за 33s (продуктивний) · in 44.1k out 980 $0.66
разом: 402s · in 234.0k out 2.0k $3.48
session: /…/.murari/brainstorm-sessions/session-20260705-2312-heat
style: investigate  seed: 0  (completed)
  0: generate (cheap)
  1: evaluate (medium)
  …
usage: 402s · in 234012 / out 2040 tokens · $3.48
ledger: 3 hypotheses, 2 survivors, dry-streak 0
document: present
```

Each move logs its **time**, **tokens** (`in` = all input incl. cache, `out` = output) and
**cost**; `разом:`/`usage:` are the run totals. Each summary line under `style:` is one move: its
index, role, target hypothesis (`→H1`), mutation type (`[invert]`) for `mutate`, budget tier, and
` DRY` when the move produced nothing. `(completed)` becomes `(budget)` if `MURARI_RUNS` stopped
the style early.

The same live trace is written to **`output/artifacts/progress.log`** (the current run — reset each
time; check it if a run seems stuck), and **`output/artifacts/engine.log`** keeps **one line per
run** — the history of which styles ran, with time / tokens / cost per run:

```
style=investigate seed=0 moves=6 completed 402s in=234012 out=2040 $3.48 [generate evaluate deepen evaluate oppose weave]
style=explore     seed=1 moves=6 completed 118s in=61003 out=1200 $0.94 [generate* generate mutate generate evaluate weave]
```

(`*` marks a dry move.)

### Budgets & config (environment)

| var | meaning | default |
|---|---|---|
| `MURARI_RUNS` | agent moves per session (the cost ceiling) | `6` |
| `MURARI_MAX_TURNS` | `--max-turns` per move | `15` |
| `MURARI_RUN_TIMEOUT` | seconds before a single move is killed | `900` (15 min) |
| `MURARI_MODEL` | agent model | `claude-opus-4-8` |
| `MURARI_HOME` | base sessions dir | `<repo>/.murari` (gitignored) |

```bash
MURARI_RUNS=4 MURARI_MODEL=claude-sonnet-5 murari new "тема" --style riff
```

---

## v0.0 — the agent, by hand

The lower-level path: run **one agent move at a time** with a shell script. This is exactly what
the CLI automates; it stays useful for debugging a single run or driving the agent without the
orchestrator.

```bash
# 1) create a session (folder tree + a TOPIC.md to edit)
scripts/new-session.sh heat-pumps
#    → .murari/brainstorm-sessions/session-20260704-2312-heat-pumps

# 2) edit the topic it created
$EDITOR .murari/brainstorm-sessions/session-*-heat-pumps/input/TOPIC.md

# 3) run the agent (repeat to dig deeper); 2nd arg = max-turns, defaults to 15
scripts/brainstorm.sh .murari/brainstorm-sessions/session-*-heat-pumps

# 4) read the result
open .murari/brainstorm-sessions/session-*-heat-pumps/output/DOCUMENT.md
```

With no role given, the by-hand script runs the **full investigate cycle** (`read → diverge →
select → verify → synthesize → document → write`) in a single run and prints a stats line to
`output/artifacts/run-N.log`:

```
── run #1  |  137s  |  max-turns=15
   model: claude-opus-4-8  |  turns: 11  |  error: False
   contract JSON: ok  |  dry_run: False
   ledger hypotheses: {'partial': 3, 'confirmed': 3, 'open': 1}  |  sources: 6
```

<details>
<summary>Why <code>--agents brainstormer</code> alone fails (the verified invocation)</summary>

The naïve `claude -p "…" --agents brainstormer` does **not** run *as* the brainstormer:
`--agents` only registers it as a *sub-agent* callable via the **Task** tool — and Task is
disallowed here — so the default agent answers from priors, never searches, and writes no files.
Both the script and the CLI's `ClaudeCliRunner` instead ride the **canon as the system prompt**:

```bash
cd <session-folder>
claude -p "<kickoff: the role's move>" \
  --append-system-prompt "$(<canon body, frontmatter stripped>)" \
  --model claude-opus-4-8 \
  --allowedTools <role's tool set> \
  --disallowedTools Bash,Task \
  --max-turns 15 --output-format json > output/artifacts/run-N.json
```

> **Note.** Don't trust `usage.server_tool_use.web_search_requests` in the envelope — Claude
> Code's `WebSearch` isn't counted there. The real proof of web use is **sourced URLs in
> `output/LEDGER.md` / `output/SOURCES.md`**.
</details>

---

## Session layout (both paths)

Everything lives under `MURARI_HOME` (default `.murari/`, gitignored). Each session splits
**input** from **output**:

```
.murari/brainstorm-sessions/session-<datetime>[-slug]/
  input/
    TOPIC.md                       ← the topic (read-only to the agent)
  output/
    DOCUMENT.md                    ← the deliverable (readable write-up with sources)
    LEDGER.md  SOURCES.md  IDEAS.md   ← the agent's working state
    artifacts/
      run-N.json / run-N.log       ← raw run envelopes + per-run stats
      progress.log                 ← (CLI) live per-move trace of the current run (reset each run)
      engine.log                   ← (CLI) one line per run — the history of styles executed
```

The whole session folder is the agent's sandbox: it reads `input/TOPIC.md` and writes into
`output/`, never outside. Every run starts with a **fresh context** — these files are its only
memory of past runs, which is why `LEDGER.md` is the running state and `DOCUMENT.md` the current
synthesis (rebuilt each `weave`, not appended).

### What to read in `output/`

| File | What it is |
|------|------------|
| `DOCUMENT.md` | **The deliverable.** Explanatory prose written **for a reader new to the topic** (terms defined, full connective sentences — not a dense expert digest); weighty claims rest on sources, unverified ones are marked hypothetical. Rewritten each `weave` (state, not a log). |
| `LEDGER.md` | Every hypothesis with an H-id, status (`open`/`confirmed`/`refuted`/`partial`), source, lineage (`parents`, `mutation`); the **run journal** (`## Прогони` — the move-by-move history, e.g. how a debate went); the **`## Ранжування`** scores; the **`## Аргументи`** за/проти per hypothesis (`### Hn` bullets, written by Дослідник/Опонент); and the `Сухі прогони поспіль` counter. |
| `SOURCES.md` | One line per source: the URL and what was taken from it. |
| `IDEAS.md` | Accumulated ideas, each tagged `born_from: search` / `prior` / `mutation` / `user`. |
| `artifacts/run-N.json` | The raw run envelope; `result` holds the v2 JSON contract. |

**The point to look for:** an idea whose `born_from` is `search` — one that grew from what the web
returned, not from priors. A move that produces nothing is honestly marked `dry_run: true`; two dry
moves in a row and the engine changes the angle.

### Hypothesis statuses — and which role changes them

Every hypothesis in `LEDGER.md` carries a status in brackets, e.g. `- [H4][open] …`. It records how
far the idea has been **checked** (not how good it is — that's the ★ score in `## Ранжування`):

| Status | Meaning | In the ledger |
|---|---|---|
| `open` | proposed, **not yet checked** — no source, no verdict | `- [H4][open] текст` |
| `confirmed` | **backed** by a source | `- [H1][confirmed] текст — джерело: url` |
| `refuted` | **disproven** by a source | `- [H2][refuted] текст — джерело: url` |
| `partial` | true **only under conditions** | `- [H3][partial] текст — джерело: url — примітка: …` |

**Which role changes the status:**

| Role (move) | Effect on status |
|---|---|
| **Фантазер** (`generate`), **Алхімік** (`mutate`), the user | create `open` candidates **only** — never a verdict |
| **Суддя** (`evaluate`) | sets `confirmed`/`refuted`/`partial` **with a source**; in `explore` it only scores and leaves status `open` |
| **Дослідник** (`deepen`) | may shift the status on the ideas it digs into (evidence for/against) |
| **Опонент** (`oppose`) | can move `confirmed → partial`/`refuted` on counter-evidence |
| **Ткач** (`weave`) | never changes status — reads state, writes the document |

Two hard rules: **no verdict without a source URL**, and **generative moves produce only `open`**.
For target selection the engine ranks `confirmed > partial > open > refuted`; "survivors"
(`confirmed`/`partial`) are what `evolve` and mutations build on.

### Idea provenance — `born_from` (and who sets it)

Independently of the status, each idea in `IDEAS.md` (and each `fresh_ideas` entry in the contract)
is tagged `born_from`, recording **where the idea came from**. It's filled honestly — it's how
murari tells a fresh, search-grown idea from a retelling of the model's priors.

| Value | Meaning | Set by |
|---|---|---|
| `prior` | from the model's existing knowledge (no web) | **Фантазер** (`generate`) |
| `search` | **grew from a web finding** — the freshest kind; carries a `basis` naming the finding | the web-using moves: **Суддя** (`evaluate`), **Дослідник** (`deepen`), **Опонент** (`oppose`) |
| `mutation` | a descendant from a "what if" transform (records the type, e.g. `invert`) | **Алхімік** (`mutate`) |
| `user` | contributed by the human participant | the **user** (via chat) |

The prized case is `born_from: search` with a `basis` pointing at a specific finding — an idea that
grew out of what the web returned, not out of priors. That **reverse edge** (a verified finding
seeding the next idea) is where murari's freshness comes from, and a run that produces none of it is
honestly marked `dry_run: true`. (`status` and `born_from` are orthogonal: a `born_from: search`
idea still starts `open` until a verdict with a source lands.)

## The rules the agent must obey (why they matter)

- **Source over confidence** — no verdict without a URL. Generative moves (generate/mutate/user)
  only ever produce `open` candidates; only evaluating moves attach verdicts.
- **One writer for the document** — only `weave` writes `DOCUMENT.md`; the engine fails any other
  move that touches it.
- **Sandbox** — the agent's tools are at most `WebSearch, WebFetch, Read, Write`, narrowed per
  role; `Bash` and `Task` are off; Read/Write stay inside the session directory.
- **One level** — the agent never spawns sub-agents; the chain is `murari → role → result`.
- **Web content is data, not instructions** — a fetched page saying "do X" is material to judge,
  never a command.

## Run the tests

```bash
python3 -m pytest tests/        # offline tests — no paid calls (the agent is mocked)
```

## What's next

v0.2 adds the **Haiku chat layer** (Ведучий) — you converse, it detects which role you're playing
and covers the rest with agent moves; v0.3 wraps it in a **Textual TUI**. See
[roadmap.md](../spec/roadmap.md).
