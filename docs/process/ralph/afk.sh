#!/usr/bin/env bash
# Repeat Ralph until NO MORE TASKS or the iteration cap.
# Usage: bash docs/process/ralph/afk.sh <iterations> [feature-slug]
#        RALPH_AGENT=cursor ... runs Cursor's agent instead of Claude Code (see lib.sh).
set -eo pipefail

# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
ralph_cd_root

if [ -z "${1:-}" ]; then
  echo "Usage: $0 <iterations> [feature-slug]"
  exit 1
fi

iterations="$1"
feature="${2:-}"

for ((i=1; i<=iterations; i++)); do
  tmpfile=$(mktemp)
  trap 'rm -f "$tmpfile"' EXIT

  commits=$(ralph_recent_commits)
  issues=$(ralph_collect_issues "$feature")
  prompt=$(cat docs/process/ralph/prompt.md)

  ralph_run_agent "Previous commits:

$commits

Issues:

$issues

Instructions:

$prompt" \
  | tee "$tmpfile" \
  | jq --unbuffered -rj "$RALPH_STREAM_TEXT"

  echo

  result=$(jq -r "$RALPH_SUCCESS | .result // empty" "$tmpfile")

  rm -f "$tmpfile"
  trap - EXIT

  if [[ "$result" == *"<promise>NO MORE TASKS</promise>"* ]]; then
    echo "Ralph complete after $i iterations."
    exit 0
  fi
done
