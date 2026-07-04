# Captured by-hand run (MUR-003)

Real, paid by-hand run of the brainstormer agent — the deliberate exception to the
"no paid APIs" rule (see roadmap §v0.0). These artifacts seed the v0.0 contract tests
(`tests/test_agent_output_contract.py`, `tests/test_workspace_format.py`).

## Topic

`tests/fixtures/session-2026-07-04-1400-teplovi-nasosy/TOPIC.md` — gas boiler vs air
heat pump for a private house in Ukraine, with two skeptical seeds.

## Exact invocation (per run)

Runs from the session directory, with the canon body (frontmatter stripped) as the
**main system prompt** — NOT `--agents brainstormer` (see the finding below).

```bash
sed '1,/^---$/d' .claude/agents/brainstormer.md > /tmp/brainstormer-body.md
claude -p "<kickoff prompt: run one cycle over TOPIC.md; create LEDGER/SOURCES/IDEAS/DOCUMENT; return only the JSON contract>" \
  --append-system-prompt "$(cat /tmp/brainstormer-body.md)" \
  --model claude-opus-4-8 \
  --allowedTools WebSearch,WebFetch,Read,Write \
  --disallowedTools Bash,Task \
  --max-turns 15 --output-format json > run-N.json
```

- **Runs:** 2 (run-1 then run-2; run-2's prompt says to read the existing LEDGER and not
  re-check closed hypotheses).
- **Model:** `claude-opus-4-8` (envelope `modelUsage` also lists `claude-haiku-4-5` — Claude
  Code's internal helper model; expected).

## Files

| File | What |
|------|------|
| `run-1.json`, `run-2.json` | raw Claude Code run envelopes; `result` holds the agent's JSON contract |
| `LEDGER.md` / `SOURCES.md` / `IDEAS.md` / `DOCUMENT.md` | workspace after run-2 |
| `after-run-1/LEDGER.md` | ledger snapshot after run-1 (for the accumulation test) |

## DoD evidence

- **Valid contract** — `result` parses to `{hypotheses, fresh_ideas, next_probes, document_delta, dry_run}` (after stripping a ```json fence).
- **Accumulation** — ledger grew 5 → 7 hypotheses; confirmed verdicts 1 → 3; the two run-1 `open` items were driven to `confirmed`; no closed verdict re-checked.
- **Traceable ideas** — `IDEAS.md` has `born_from: search` ideas with a `basis`; `LEDGER.md`/`SOURCES.md` carry real source URLs.
- **Document is state** — `DOCUMENT.md` is coherent, restructured prose (7 sections), not a per-run log.

## Findings (folded into spec/architecture.md)

1. `claude -p --agents brainstormer` does **not** run as the agent (Task disabled → sub-agent
   can't be invoked). Use `--append-system-prompt` with the canon body.
2. The model wraps the JSON contract in a ```json fence; the parser strips an optional fence.
3. `usage.server_tool_use.web_search_requests` reads `0` in Claude Code even when the agent
   searched — trust the sourced URLs in `LEDGER.md`/`SOURCES.md` instead.
