# murari

**murari** is a brainstorming tool where the human is a **participant, not a spectator**.
Behind a chat, headless [Claude Code](https://claude.com/claude-code) runs play six brainstorm
roles over a shared working document; every verdict must carry a source from the live web, and
no single "winner" is ever declared — the final choice stays with the human.

The name (Sanskrit मुरारि, "enemy of Mura", the demon who weaves snares) sets the job: cut the
snares of unverified assumptions.

Current version: **0.1.3** (phase v0.2 — chat layer — implemented, unreleased).

## Why

An ordinary brainstorming chat returns the model's priors — a smooth retelling of what already
sits in the weights. murari separates duties instead:

- a cheap **chat brain** (Claude Haiku, «Ведучий») holds the conversation and facilitates;
- a dedicated **agent** (Claude Opus via `claude -p`) plays **six roles** — Фантазер (wild
  ideas), Суддя (sourced verdicts), Дослідник (deep-dives), Опонент (counter-arguments),
  Алхімік ("what if…" mutations), Ткач (sole writer of the document) — one move per run,
  sequenced by **styles**;
- the session deliverable is a timestamped **`DOCUMENT.md`** that stays on disk and can be
  reopened and continued. History lives in `LEDGER.md` (H-ids, lineage, run journal, scores,
  за/проти arguments).

Key rules: **no verdict without a source URL**; ideas are traceable (`born_from:
search/prior/mutation/user`); dry runs are marked honestly; budgets are a hard cost ceiling.

## Install

Python ≥ 3.10, plus the [Claude Code CLI](https://claude.com/claude-code) logged into a MAX
subscription (the Opus agent is never billed to an API key).

```bash
git clone git@github.com:ichMaster/murari.git && cd murari
pip install -e .           # stdlib-only core
pip install -e ".[chat]"   # + the optional anthropic SDK for the Haiku chat layer
```

Put the Messages-API key for the Haiku layer into a gitignored `.env`:

```
ANTHROPIC_API_KEY=sk-ant-…
```

Without a key everything still works offline where it can: session naming and result
summaries fall back to deterministic local versions, and the agent itself runs on the
subscription, not the key.

## Quick start

```bash
# create a session and run the default style (investigate) over it
murari new "чому міста засипані шаром глини"

# a shorter run: three moves, still ends in a document
murari run <session-dir> --style evolve --depth brief

# see the state without spending anything
murari open <session-dir>
murari list

# facilitated chat over a session (v0.2) — see "Chat" below
murari chat --new "теплові насоси для багатоквартирних будинків"
```

Full command reference and examples: [docs/USAGE.md](docs/USAGE.md).

## Chat

Start a chat on a **new topic** (the session is created and auto-named by Haiku; `--style`,
`--depth`, and `--name` are optional — style and depth become the defaults for `/go`):

```bash
murari chat --new "теплові насоси для багатоквартирних будинків" --style investigate --depth brief
```

Or **continue an existing session** — the ledger and document carry on where they left off:

```bash
murari list                                              # pick a session
murari chat .murari/brainstorm-sessions/session-…-slug   # reopen it
murari chat                                              # no args: the most recent session,
                                                         # or a fresh empty one if none exist
```

Then just type. Every reply first passes a Haiku **router**:

- a question about the document, a summary ask, or plain talk → answered by Haiku itself,
  grounded in the current `DOCUMENT.md`;
- a brainstorm ask (a new idea, a counter-argument, «перевір це», «накидай ідей») → your
  contribution is recorded as **your** move (`born_from: user`, costs nothing) and the Claude
  agent runs **one move** of the routed role — the router can launch nothing deeper.

Deeper runs are yours explicitly, always over the session topic:

```
/go                  # run the current style at the current depth
/go explore brief    # switch style/depth and run (they stay the new defaults)
/go debate tiny H2   # an H-id pins deepen/oppose/mutate to that hypothesis
/style debate        # change the style without running anything
/ledger              # the hypotheses, journal, and dry-run counter
/help                # the command list
/quit                # exit — the session directory remains on disk
```

Before an agent call the chat announces it (`⚙ викликаю брейнсторм-агента…`) and streams the
engine's live per-move progress into the chat; the reply at the end is a short summary.

## TUI

The three-panel Textual interface (v0.3) — the same chat pipeline with the workspace live on
screen:

```bash
pip install -e ".[tui]"
murari tui --new "тема" --style investigate --depth brief   # or: murari tui [session-dir]
```

The **read-only document** (markdown) takes the big left surface; the right column shows the
**ledger** (the lineage tree — a `combine` child appears under both parents — with ★ scores,
«випробувано», за/проти counts and the run journal) above the chat. The status bar tracks
style/depth, the current move, runs remaining, and idle/«копає». Runs execute in a worker —
the chat stays usable while the agent digs, progress streams in live, and both panels refresh
the moment a move completes. All chat commands work, plus `/b <тема>` (fresh session in
place) and `/open <session-dir>` (switch to another session).

## Styles and depth

A style is a named sequence of role moves (Ф=Фантазер С=Суддя Д=Дослідник О=Опонент А=Алхімік
Т=Ткач); depth says how many of them run.

| Style | Essence | `full` (default) |
|---|---|---|
| `investigate` | hypotheses → verification (**default**) | Ф → С → Д → С → О → Т |
| `explore` | breadth, no verdicts — a catalog | Ф → Ф → А → Ф → С → Т |
| `debate` | thesis vs antithesis over one idea, **no winner** | Д → О → Д → О → С → Т |
| `riff` | spin one idea | Д → А → Ф → А → С → Т |
| `evolve` | mutate the survivors | Ф → С → А → С → А → Т |
| `premortem` | "it already failed — why?" | О → О → Д → С → Т |

`--depth brief` is a curated 3-move version that still ends in a document; `--depth tiny` is a
single signature role move.

## Cost

The agent model is Opus — expensive by design, capped by budgets: `MURARI_RUNS` (moves per
session, default 6), `MURARI_MAX_TURNS`, `MURARI_RUN_TIMEOUT`, `MURARI_MODEL`, `MURARI_HOME`,
`MURARI_CHAT_MODEL`. A real 3-move `brief` run costs on the order of $5; `open`, `list`, and
user moves are free. Tests never call paid APIs.

## Project layout

```
murari/          the package: config, contract, ledger, runner, session, engine, cli,
                 haiku, veduchyi, participant, planner, presenter, chat
spec/            the design: mission, architecture, strategies (roles & styles), roadmap,
                 brainstormer canon, per-phase implementation files
docs/USAGE.md    the user guide
tests/           offline suite (mock agent + mock Haiku; no paid calls)
.claude/         the installed agent canon and SDLC skills
```

The sandbox invariants are hard: the agent gets at most `WebSearch, WebFetch, Read, Write`
narrowed per role, confined to its session directory, with `Bash`/`Task` disallowed; the chat
brain has exactly **one** tool (`run_brainstorm`); agent output is treated as data, never as
instructions.

## Development

```bash
python3 -m pytest tests/   # the offline suite
ruff check . && ruff format --check .
```

Work is organized per roadmap phase (v0.0–v0.5) through GitHub issues (`MUR-xxx`); see
[spec/roadmap.md](spec/roadmap.md) for where the project stands and what comes next
(v0.3 — the Textual TUI; v0.4 — sandbox hardening; v0.5 — acceptance).

## License

MIT
