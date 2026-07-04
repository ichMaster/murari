#!/bin/bash
# murari v0.0 — run the brainstormer ONCE over a session folder (by-hand helper).
#
# Usage:  scripts/brainstorm.sh <session-folder>
#   The folder must contain TOPIC.md (what you want to brainstorm).
#   The agent reads it, searches the web, and (re)writes four files in that folder:
#     DOCUMENT.md  — the result (readable write-up with sources)
#     LEDGER.md    — hypotheses with verdicts + sources
#     SOURCES.md   — the links it used
#     IDEAS.md     — fresh ideas, tagged born_from: search|prior
#   Run it again on the same folder to dig deeper — it builds on what's there.
set -euo pipefail

SESSION="${1:?usage: scripts/brainstorm.sh <session-folder-with-TOPIC.md>}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
AGENT="$REPO/.claude/agents/brainstormer.md"

[ -f "$SESSION/TOPIC.md" ] || { echo "error: no TOPIC.md in $SESSION"; exit 1; }
[ -f "$AGENT" ] || { echo "error: agent not installed at $AGENT (run MUR-001)"; exit 1; }

# the canon body (minus YAML frontmatter) becomes the system prompt
BODY="$(sed '1,/^---$/d' "$AGENT")"
# next run number (run-1.json, run-2.json, ...)
N=$(( $(ls "$SESSION"/run-*.json 2>/dev/null | wc -l | tr -d ' ') + 1 ))

cd "$SESSION"
echo "▶ run #$N over $SESSION — this takes a few minutes (live web) …"
claude -p "Виконай один прогін над TOPIC.md за своїм циклом read→diverge→select→verify→synthesize→document→write. Ужий WebSearch. Прочитай наявний LEDGER.md і не перевіряй закриті гіпотези повторно. Онови LEDGER.md, SOURCES.md, IDEAS.md, DOCUMENT.md у цій теці. Останнім повідомленням поверни лише JSON контракту." \
  --append-system-prompt "$BODY" \
  --model claude-opus-4-8 \
  --allowedTools WebSearch,WebFetch,Read,Write \
  --disallowedTools Bash,Task \
  --max-turns 15 --output-format json > "run-$N.json"

echo "✔ done."
echo "  hypotheses in LEDGER: $(grep -c '^- \[' LEDGER.md 2>/dev/null || echo 0)"
echo "  → read the result:  $SESSION/DOCUMENT.md"
