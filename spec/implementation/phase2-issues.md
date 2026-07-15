# Phase v0.2 — GitHub Issues

Issues for phase **v0.2 — Chat layer: Ведучий (Haiku)** (version **v0 — the prototype**), derived
from the per-phase Goal / Tasks / DoD / Tests in [roadmap.md](../roadmap.md) (§v0.2) and the
contracts in [architecture.md](../architecture.md) and [strategies.md](../strategies.md) (roles &
styles, accepted 2026-07-05). This file is scoped to a single phase; IDs continue from the
previous phase (MUR-011 → **MUR-012…MUR-017**).

v0.2 puts a conversation in front of the v0.1 style engine: a **Claude Haiku** loop (Ведучий, no
persona) that detects which brainstorm role the user is playing, closes the remaining roles with
complementary agent moves (adversarial only in `debate`, no winner), and presents results in human
language — with **exactly one tool**, `run_brainstorm(seed, role, target_idea?, mutation_type?,
style_step?, depth?)`. The Haiku model seam arrives here, first used to auto-name sessions. No new
roles; no TUI (that is v0.3) — the chat runs as a headless REPL over the existing CLI.

## Issues Summary Table

| # | ID | Title | Size | Area | Phase | Dependencies |
|---|----|-------|------|------|-------|--------------|
| 1 | MUR-012 | Haiku model seam + session auto-naming (Namer, local fallback) | M | chat | p2 | -- |
| 2 | MUR-013 | Ведучий loop: facilitation prompt, single-tool boundary, dispatch | M | chat | p2 | MUR-012 |
| 3 | MUR-014 | Role detection + user moves: provenance, journal, H-id allocation | M | chat | p2 | MUR-012 |
| 4 | MUR-015 | Move planner: complementarity, debate pairing, style selection | M | chat | p2 | MUR-014 |
| 5 | MUR-016 | Seed extraction + result presentation (output is data) | S | chat | p2 | MUR-013 |
| 6 | MUR-017 | Chat REPL: commands, trigger policy, integration turn | M | chat | p2 | MUR-013, MUR-014, MUR-015, MUR-016 |

**Size legend:** S = 1–2 days, M = 3–5 days, L = 5–8 days
**Area:** agent · chat · tui · orchestrator · sandbox · tests · spec

---

## Dependency Tree

```
MUR-012 (Haiku model seam + Namer)
  |
  +-- MUR-013 (Ведучий loop + single tool) --+-- MUR-016 (seeds + presentation) --+
  |                                          |                                    |
  +-- MUR-014 (role detection + user moves) -+-- MUR-015 (move planner) ----------+
                                                                                  |
                                                MUR-017 (chat REPL + integration)
                                                  => v0.2 DoD (a facilitated chat turn)
```

**Parallelization hints:** MUR-012 first (gate — every other issue consumes the model seam).
Then MUR-013 and MUR-014 in parallel; MUR-015 and MUR-016 follow their own tracks. MUR-017
integrates everything into the REPL and the phase DoD.

---

## v0.2 — Chat layer: Ведучий (Haiku)

### MUR-012 — Haiku model seam + session auto-naming (Namer, local fallback)

**Description:**
Introduce the **Haiku model seam** — the one place that talks to the Anthropic Messages API —
behind a thin, mockable interface, and use it for its first job: **auto-naming a session**.
Touches: **chat** (+ the CLI's `new`/`list`/`open` rendering). Billing note: Haiku is the metered
Messages API (key in gitignored `.env`) — never the MAX subscription; CI never calls it.

**What needs to be done:**
- `murari/haiku.py`: a `HaikuModel` protocol (messages in → text/tool-use out) + the real
  HTTP-API client (model + max-tokens from config; key from `ANTHROPIC_API_KEY` via the existing
  `.env` loader; the `anthropic` SDK as an **optional** dependency) + `MockHaikuModel` for tests
  (scripted replies, records what it was asked).
- `Namer` seam on top: on `new`, ask Haiku for a short Ukrainian title from the topic and write
  it as a `# <name>` heading above the topic in `input/TOPIC.md`; **`local_name` fallback**
  (missing key / no SDK / network error → derive a slug-title from the topic text) so naming
  never blocks and never throws; explicit `--name` still overrides (no Haiku call at all).
- `list` shows the session name next to the folder (reads the TOPIC.md heading); `open` prints
  it too; sessions without a heading (pre-v0.2) render unchanged.
- **Workspace-format seam:** TOPIC.md gains the optional `# <name>` heading — update
  [architecture.md](../architecture.md) (session workspace table) and pin the format in the same
  issue: the heading is chat-written, the agent still treats TOPIC.md as read-only input.

**Dependencies:** None

**Expected result:**
`murari.haiku` is the single mockable gateway to the Haiku API, and a fresh `new` gets a
Ukrainian title in TOPIC.md (Haiku when a key is present, local fallback otherwise) that
`list`/`open` display.

**Acceptance criteria:**
- [ ] **Unit test:** mock Namer → TOPIC.md carries the `# <name>` heading above the topic;
      `--name` bypasses the model; the agent-facing topic body is unchanged.
- [ ] **Unit test:** local fallback — no key / no SDK / a raising mock → a deterministic local
      title, no exception, no network (CI makes no paid call).
- [ ] **Unit test:** `list` renders the name next to the folder; heading-less sessions render as
      today; `open` prints the name.
- [ ] **Contract test:** TOPIC.md format pinned — heading optional, topic body intact, agent
      side reads the same topic with and without a heading.
- [ ] Ties to roadmap §v0.2 Tasks "Session naming (Haiku)" and "`list` shows the session name".

---

### MUR-013 — Ведучий loop: facilitation prompt, single-tool boundary, dispatch

**Description:**
The Ведучий core: a Haiku conversation loop over the model seam whose system prompt frames
**facilitation** (no persona), with **exactly one tool** registered —
`run_brainstorm(seed, role, target_idea?, mutation_type?, style_step?, depth?)` — dispatched by
deterministic Python into the v0.1 engine. Touches: **chat** (+ the Tier-1 sandbox seam).
Chat/product language is Ukrainian per conventions.

**What needs to be done:**
- `murari/veduchyi.py` (or `chat.py`): the turn loop — user text in, Haiku reply and/or a single
  `run_brainstorm` tool call out; conversation history kept in memory for the session (no
  implicit cross-session memory).
- Facilitation system prompt (Ukrainian): frame the topic, hold the dialogue, facilitate roles —
  explicitly **not** a persona; instruct that agent output and web content are quoted data.
- **Single-tool boundary:** the API request's tool list contains exactly `run_brainstorm`; its
  JSON schema mirrors the accepted signature with `depth: full|brief|tiny` (roadmap v0.2
  extension). No filesystem, Bash, or web tool is ever registered for Tier 1.
- Deterministic dispatch: **validate tool args as data** before running — role key in the six,
  `target_idea` exists in the ledger, `mutation_type` in the five, `depth` in the three; invalid
  args → a structured refusal back to Haiku, not an exception, and never a run. Valid args map
  onto the engine (single role move, or a style step at the given depth) with budgets intact.
- **Seam change lands with its docs:** update [architecture.md](../architecture.md) Tier-1
  section — the tool signature gains `depth` (strategies.md §Ведучий already extends it) — plus
  the boundary contract test below, in this same issue.

**Dependencies:** MUR-012

**Expected result:**
A chat turn flows user → Haiku → (optionally) one validated `run_brainstorm` → engine → reply,
and Haiku can initiate nothing else.

**Acceptance criteria:**
- [ ] **Contract test:** the single-tool boundary — the request built for the Haiku API exposes
      exactly one tool named `run_brainstorm` with the accepted signature (incl. `depth`); a
      scripted mock asking for any other tool gets a refusal and no side effect.
- [ ] **Unit test:** dispatch validation — bad role / unknown H-id / bad mutation type / bad
      depth each refuse without launching; a valid call reaches a `MockAgentRunner`-backed
      engine and returns its result.
- [ ] **Unit test:** budgets flow through — a call beyond `MURARI_RUNS` is refused the same way
      the CLI refuses it.
- [ ] Ties to roadmap §v0.2 Tasks "Haiku loop … no persona" and "Register the single tool", and
      the sandbox invariant "Tier 1: exactly one tool".

---

### MUR-014 — Role detection + user moves: provenance, journal, H-id allocation

**Description:**
Make the human the seventh player: classify each substantive reply into a brainstorm role (or
"just steering"), and record user contributions in the shared state with honest provenance.
Touches: **chat** (classification) + the deterministic write side of the workspace (journal,
IDEAS, ledger candidates). The write side is plain Python — Haiku itself still touches no files.

**What needs to be done:**
- Role detector on the Haiku seam: a reply → one of Фантазер / Дослідник (brings material) /
  Опонент / Алхімік / Суддя-замовлення / Ткач-замовлення / "steering" — per the reply table in
  [strategies.md](../strategies.md) §"Користувач як учасник"; low-confidence → steering (never
  guess a move).
- Deterministic user-move writer: a classified contribution allocates the next H-id via the
  ledger helpers and lands as an `open` candidate (`born_from: user`) in LEDGER/IDEAS; a journal
  line `- N: <role>(користувач) → …` records the executor; Ткач-замовлення records the order for
  the next weave instead of editing DOCUMENT.md (ownership invariant).
- **Source gate holds:** user contributions are always `open` — a user "verdict" is a Суддя
  *order* (a future evaluate move), never a status change.
- User moves are free: they consume no `MURARI_RUNS` budget (config seam already counts agent
  moves only — assert it).

**Dependencies:** MUR-012

**Expected result:**
A user reply lands in the workspace exactly like a role move — classified, journaled,
provenance-marked — without spending budget or touching DOCUMENT.md.

**Acceptance criteria:**
- [ ] **Unit test:** role detection over labeled replies (mocked Haiku) — one fixture per role
      per the strategies table, plus a steering reply and a low-confidence case → steering.
- [ ] **Unit test:** user-move writer — H-id allocated sequentially, `[Hn][open] … —
      born_from: user`, journal line with `(користувач)`, IDEAS entry; formats parse back
      through the pinned LEDGER v2 tests unchanged.
- [ ] **Unit test:** source gate — a user reply claiming "confirmed" still lands `open`;
      Ткач-замовлення never writes DOCUMENT.md.
- [ ] **Unit test:** budget — user moves leave `MURARI_RUNS` untouched.
- [ ] Ties to roadmap §v0.2 Task "Role detection" and the strategies provenance decision
      (`born_from: user`, journal executor).

---

### MUR-015 — Move planner: complementarity, debate pairing, style selection

**Description:**
The facilitation brain's deterministic half: given the style, the ledger state, and the user's
live role, choose the next agent move. Complementarity by default (never duplicate the user's
role), **adversarial pairing only in `debate`** (and no winner declared), style selection and
mid-session change. Touches: **chat** (planning logic; the engine already executes moves).

**What needs to be done:**
- `plan_next_move(style, ledger_state, user_role, depth?) → move`: complementarity — the next
  agent move never duplicates the user's live role (an actively opposing user suppresses
  `oppose` and favors `deepen`/`evaluate`); target selection reuses the engine's
  strongest-survivor rules.
- `debate` exception: deliberately pair *against* the user's side (user defends → agent
  `oppose`, user attacks → agent `deepen`/defends); sides may swap; **no winner is ever
  declared** — planner output frames both sides' arguments as the product.
- Style selection: explicit `/style <key>` always wins; otherwise infer from the topic framing
  via the Haiku seam (a question → `investigate`, "накидай варіантів" → `explore`, …) with
  `investigate` as the safe default; style can change mid-session without restarting.
- Honor the engine's deviation rule (two dry moves → deviate): the planner surfaces the engine's
  justification into the chat rather than fighting it; record the v0.1–v0.2 open question
  ("style deviation rules") as closed-for-v0.2 in the roadmap with whatever rule ships.

**Dependencies:** MUR-014

**Expected result:**
For any (style, ledger, user-role) state the planner returns one defensible next move — never
the user's own role outside `debate`, always adversarial inside it, never a winner.

**Acceptance criteria:**
- [ ] **Unit test:** complementarity matrix — for each style × user-role, the planned move never
      duplicates the user's role (except `debate`); the opposing-user case favors
      `deepen`/`evaluate`.
- [ ] **Unit test:** `debate` pairing — user side in, opposite agent role out; swapped sides
      swap the pairing; planner output contains no winner declaration.
- [ ] **Unit test:** style selection — explicit `/style` wins; inference fixtures (mocked Haiku)
      map framings to styles with `investigate` fallback; mid-session change replans from the
      new template.
- [ ] Roadmap "Open questions" updated: style-deviation entry closed or narrowed by the shipped
      rule (spec + code in the same issue).
- [ ] Ties to roadmap §v0.2 Tasks "Complementarity" and "Style selection".

---

### MUR-016 — Seed extraction + result presentation (output is data)

**Description:**
The two translation layers around a run: user replies → a compact seed for `run_brainstorm`, and
the run's contract JSON → human-language chat (Ukrainian). Enforce the invariant that **agent
output and fetched web content are data, not instructions**. Touches: **chat**.

**What needs to be done:**
- Seed extraction: distill the conversation turn (topic framing, the user's contribution, the
  planned move) into the `seed` argument — topic and hypothesis content only; names/addresses/
  private details never enter the seed (the de-identification invariant starts here, hardened
  in v0.4).
- Result presentation: EngineResult + contract v2 fields (hypotheses touched, verdicts with
  sources, `dry_run`, `next_role`) → a short Ukrainian summary via the Haiku seam, with sources
  cited; dry runs reported honestly.
- **Output-is-data guard:** run output and any quoted web content pass to Haiku wrapped as
  quoted material (delimited, escaped); an output containing an instruction ("виконай X",
  "ignore previous instructions", a fake tool call) is rendered, never acted on — no tool
  dispatch may originate from run output.
- Close the v0.2 open question "presentation format": decide paraphrase-always vs raw block for
  long results, record it in roadmap/architecture (spec + code in this issue).

**Dependencies:** MUR-013

**Expected result:**
A completed move comes back as readable Ukrainian chat with sources, and nothing an agent or a
web page says can steer the chat layer.

**Acceptance criteria:**
- [ ] **Unit test:** seed extraction — fixtures with personal details (name, address, email)
      produce seeds without them; topic and hypothesis content survive.
- [ ] **Contract test:** result-as-data — a run output containing "do X" / an embedded tool-call
      shape triggers no dispatch and arrives quoted in the presentation input (regression pin
      for the sandbox invariant).
- [ ] **Unit test:** presentation — canned EngineResults (verdict with source, dry run, deviation)
      render summaries that name the sources and the dry-run honestly (mocked Haiku).
- [ ] Roadmap "Open questions" updated: presentation-format entry closed by the shipped decision.
- [ ] Ties to roadmap §v0.2 Task "Seed extraction and result presentation" and the invariant
      "The agent's output is data, not instructions".

---

### MUR-017 — Chat REPL: commands, trigger policy, integration turn

**Description:**
Assemble the phase: a headless chat REPL (`murari chat`, the v0.3 TUI's stand-in) wiring the
loop, detector, planner, and presenter over a session — plus the trigger-policy decision.
Touches: **chat** (+ tests). Integrates MUR-013/014/015/016 into the v0.2 DoD.

**What needs to be done:**
- `murari chat [session|--new "<topic>"]`: REPL over stdin/stdout — new sessions get the
  MUR-012 naming flow; reopened ones resume from the existing workspace (explicit continuation,
  no implicit memory).
- In-chat commands: `/style <key>` (MUR-015), `/go` (force the planned move), `/ledger` (render
  current H-ids/lineage/journal read-only), `/quit` (exit; the session dir remains).
- **Close the trigger-policy open question (v0.2 scope):** does a substantive on-topic reply
  auto-launch the planned move, or only `/go`? Ship one behavior, record the decision in the
  roadmap decision register (spec + code together).
- Full-turn flow: reply → detect role → record user move → plan → (auto or `/go`) dispatch →
  present result; errors from the engine degrade to a chat message, never a crash or a corrupted
  workspace.
- **Integration test (the phase DoD as a script):** on mock Haiku + `MockAgentRunner` — a
  substantive reply is classified, the complementary move launches with the right kickoff, the
  result renders in human language with sources; a `debate` turn pairs adversarially and
  declares no winner; `/quit` leaves the named session on disk and `chat <session>` continues it.

**Dependencies:** MUR-013, MUR-014, MUR-015, MUR-016

**Expected result:**
One command opens a facilitated brainstorm chat: the user plays a role, the system plays the
rest, results come back in Ukrainian, and Haiku can initiate nothing but `run_brainstorm`.

**Acceptance criteria:**
- [ ] **Unit test:** command parsing (`/style`, `/go`, `/ledger`, `/quit`) and the trigger
      policy as decided.
- [ ] **Integration test:** the full chat turn per the description — mock Haiku + mock agent,
      no paid APIs, asserting workspace deltas (journal, provenance) and the rendered reply.
- [ ] **Integration test:** reopen-and-continue through the REPL — a second `chat <session>`
      builds on the first's ledger and document.
- [ ] Roadmap decision register updated: trigger policy recorded (open question closed).
- [ ] Ties to roadmap §v0.2 DoD: classified reply → correct complementary (or adversarial)
      move → human-language result; single-tool boundary holds end to end.

---

## v0.2 scope notes

**Total effort:** ~3 weeks (M+M+M+M+S+M).
**Critical path:** MUR-012 → MUR-013 → MUR-016 → MUR-017 (equal-length twin: MUR-012 → MUR-014 →
MUR-015 → MUR-017).
**Phase DoD (roadmap §v0.2):** a chat where a substantive reply is classified into a role, the
correct complementary move launches (or an adversarial one in `debate`), and results come back in
human language; Haiku can initiate nothing but `run_brainstorm`. A fresh `new` gets a
Haiku-generated title in TOPIC.md (local fallback when there is no key), and `list`/`open` show it.
**Contracts pinned this phase:** the **Haiku single-tool boundary** (exactly one tool, the
accepted signature incl. `depth`, MUR-013), the **TOPIC.md heading format** (MUR-012), the
**result-as-data guard** (MUR-016), and the **user-move provenance formats** riding the existing
LEDGER v2 pins (MUR-014).
**Open questions closed this phase:** presentation format (MUR-016), trigger policy (MUR-017),
style-deviation rules narrowed (MUR-015) — each recorded in the spec in the same issue as its code.
**Model/mock note:** CI mocks the agent (`claude -p`), the Haiku chat model, and web search —
**no paid APIs**. Haiku billing is the metered Messages API (key in gitignored `.env`, optional
`anthropic` SDK); the Namer's local fallback keeps every path key-free in CI.
**Companion documents:**
- [roadmap.md](../roadmap.md) — version goals, per-phase Goal/Tasks/DoD/Tests (§v0.2).
- [architecture.md](../architecture.md) — the two-head architecture, Tier-1 boundary, workspace, sandbox invariants.
- [strategies.md](../strategies.md) — roles, styles, the user as participant, Ведучий (accepted 2026-07-05).
- [mission.md](../mission.md) — principles and the Definition of done.
- Generated on upload: `phase2-github-report.md` (MUR-xxx → GitHub #), then `phase2-execution-report.md`.
