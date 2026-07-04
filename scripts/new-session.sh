#!/bin/bash
# murari — create a new brainstorm session under MURARI_HOME/brainstorm-sessions/.
#
# Usage:  scripts/new-session.sh [name]
#   Creates  session-<datetime>[-slug]/{input, output/artifacts}  and copies the
#   TOPIC.md template into input/. Prints the session path and next steps.
#
#   MURARI_HOME defaults to <repo>/.murari (gitignored). Override with the env var.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="${MURARI_HOME:-$REPO/.murari}"
SESSIONS="$HOME_DIR/brainstorm-sessions"
TEMPLATE="$REPO/examples/TOPIC.md"

[ -f "$TEMPLATE" ] || { echo "error: missing template $TEMPLATE"; exit 1; }

# optional slug from a name argument (ascii; non-ascii names just fall back to datetime)
SLUG=""
NAME="${1:-}"
if [ -n "$NAME" ]; then
  CLEAN="$(printf '%s' "$NAME" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' \
            | tr -cd 'a-z0-9-' | sed 's/-\{2,\}/-/g; s/^-//; s/-$//')"
  [ -n "$CLEAN" ] && SLUG="-$CLEAN"
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
SESSION="$SESSIONS/session-$STAMP$SLUG"

mkdir -p "$SESSION/input" "$SESSION/output/artifacts"
cp "$TEMPLATE" "$SESSION/input/TOPIC.md"

echo "✔ created session: $SESSION"
echo "  1) edit the topic:  $SESSION/input/TOPIC.md"
echo "  2) run it:          scripts/brainstorm.sh \"$SESSION\""
