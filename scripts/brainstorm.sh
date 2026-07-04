#!/bin/bash
# murari v0.0 — run the brainstormer ONCE over a session folder (by-hand helper).
#
# Usage:  scripts/brainstorm.sh <session-folder> [max-turns]
#   <session-folder> must contain input/TOPIC.md (see scripts/new-session.sh).
#   [max-turns] defaults to 15.
#
#   The agent reads input/TOPIC.md, searches the web, and writes into output/:
#     DOCUMENT.md  LEDGER.md  SOURCES.md  IDEAS.md
#   The raw run envelope + a stats log go to output/artifacts/run-N.{json,log}.
#   Re-run on the same folder to dig deeper — it builds on the existing ledger.
set -euo pipefail

SESSION="${1:?usage: scripts/brainstorm.sh <session-folder> [max-turns]}"
MAX_TURNS="${2:-15}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
AGENT="$REPO/.claude/agents/brainstormer.md"

[ -f "$SESSION/input/TOPIC.md" ] || { echo "error: no input/TOPIC.md in $SESSION (run scripts/new-session.sh first)"; exit 1; }
[ -f "$AGENT" ] || { echo "error: agent not installed at $AGENT"; exit 1; }

SESSION="$(cd "$SESSION" && pwd)"          # absolutize
mkdir -p "$SESSION/output/artifacts"

BODY="$(sed '1,/^---$/d' "$AGENT")"        # canon body -> system prompt
N=$(( $(ls "$SESSION"/output/artifacts/run-*.json 2>/dev/null | wc -l | tr -d ' ') + 1 ))
ENV_JSON="$SESSION/output/artifacts/run-$N.json"
LOG="$SESSION/output/artifacts/run-$N.log"

PROMPT="Робоча тека сесії — поточна тека. Прочитай тему з input/TOPIC.md і наявний стан з output/LEDGER.md (якщо існує). Виконай один прогін за своїм циклом read→diverge→select→verify→synthesize→document→write; ужий WebSearch; не перевіряй закриті гіпотези повторно. ВСІ робочі файли (LEDGER.md, SOURCES.md, IDEAS.md, DOCUMENT.md) створюй і онови в теці output/ (не в корені й не в input/). Останнім повідомленням поверни лише JSON контракту."

echo "▶ run #$N over $SESSION (max-turns=$MAX_TURNS) — a few minutes (live web) …"
START="$(date +%s)"
cd "$SESSION"
claude -p "$PROMPT" \
  --append-system-prompt "$BODY" \
  --model claude-opus-4-8 \
  --allowedTools WebSearch,WebFetch,Read,Write \
  --disallowedTools Bash,Task \
  --max-turns "$MAX_TURNS" --output-format json > "$ENV_JSON"
END="$(date +%s)"

# safety net: if the model dropped a file at the session root, move it into output/
for f in LEDGER.md SOURCES.md IDEAS.md DOCUMENT.md; do
  [ -f "$SESSION/$f" ] && mv -f "$SESSION/$f" "$SESSION/output/$f"
done

# stats -> stdout + run-N.log
python3 - "$ENV_JSON" "$SESSION/output/LEDGER.md" "$((END-START))" "$N" "$MAX_TURNS" <<'PY' | tee "$LOG"
import collections, json, re, sys
envp, ledgerp, secs, n, maxt = sys.argv[1:6]
d = json.load(open(envp))
r = d.get("result", "").strip()
if r.startswith("```"):
    r = re.sub(r"^```[a-z]*\s*\n", "", r); r = re.sub(r"\n```$", "", r)
try:
    contract = json.loads(r); ok = True
except Exception:
    contract = {}; ok = False
try:
    lt = open(ledgerp).read()
    counts = dict(collections.Counter(re.findall(r"^- \[(\w+)\]", lt, re.M)))
    sources = len(re.findall(r"джерело:\s*http", lt))
except FileNotFoundError:
    counts, sources = {}, 0
print(f"── run #{n}  |  {secs}s  |  max-turns={maxt}")
print(f"   model: {', '.join(d.get('modelUsage', {}).keys()) or '?'}  |  turns: {d.get('num_turns')}  |  error: {d.get('is_error')}")
print(f"   contract JSON: {'ok' if ok else 'MISSING'}  |  dry_run: {contract.get('dry_run')}")
print(f"   ledger hypotheses: {counts or '{}'}  |  sources: {sources}")
PY

echo "✔ done → read $SESSION/output/DOCUMENT.md"
