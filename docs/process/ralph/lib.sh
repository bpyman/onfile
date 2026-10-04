# Shared helpers for once.sh, afk.sh and afk-parallel.sh. Sourced; not executed.

# The agent that works a ticket: claude (Claude Code, billed to the Claude subscription it
# is signed in to) or cursor (Cursor's agent CLI).
RALPH_AGENT="${RALPH_AGENT:-claude}"

# jq filters over the agent's stream-json output. RALPH_STREAM_TEXT prints the agent's text
# as it arrives; RALPH_SUCCESS keeps the final result event of a run that succeeded.
case "$RALPH_AGENT" in
  claude)
    # Each assistant message arrives whole; a newline keeps one from running into the next.
    RALPH_STREAM_TEXT='
      select(.type == "assistant")
      | .message.content[]?
      | select(.type == "text")
      | (.text // empty) + "\n"
    '
    ;;
  cursor)
    # Only new streaming text, excluding Cursor's duplicate flush events.
    RALPH_STREAM_TEXT='
      select(
        .type == "assistant"
        and has("timestamp_ms")
        and (has("model_call_id") | not)
      )
      | .message.content[]?
      | select(.type == "text")
      | .text // empty
    '
    ;;
  *)
    echo "RALPH_AGENT must be claude or cursor, not '$RALPH_AGENT'" >&2
    exit 1
    ;;
esac
# Claude Code reports a run stopped by a usage limit as subtype success with is_error true.
RALPH_SUCCESS='select(.type == "result" and .subtype == "success" and ((.is_error // false) | not))'

ralph_cd_root() {
  cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
}

ralph_collect_issues() {
  local feature="${1:-}"
  local files=""
  local f status

  if [ -n "$feature" ]; then
    if [ ! -d "docs/process/tickets/${feature}/issues" ]; then
      echo "No issues found (docs/process/tickets/${feature}/issues missing)"
      return 0
    fi
    files=$(find "docs/process/tickets/${feature}/issues" -maxdepth 1 -type f -name '*.md' | sort)
  elif [ -d docs/process/tickets ]; then
    files=$(find docs/process/tickets -type f -name '*.md' -path '*/issues/*' ! -path '*/done/*' | sort)
  fi

  if [ -z "$files" ]; then
    echo "No issues found"
    return 0
  fi

  echo "Index (read ticket files from disk; bodies are not inlined):"
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    status=$(grep -m1 -E '^\*\*Status:\*\*|^Status:' "$f" || true)
    blocked=$(grep -m1 -E '^\*\*Blocked by:\*\*|^Blocked by:' "$f" || true)
    printf '  %s  %s  %s\n' "$f" "${status:-Status: (none)}" "${blocked:-}"
  done <<< "$files"
}

ralph_recent_commits() {
  git log -n 5 --format="%H%n%ad%n%B---" --date=short 2>/dev/null || echo "No commits found"
}

ralph_run_agent() {
  local payload="$1"
  local prompt_file="docs/process/tickets/.ralph-run.md"
  local short

  mkdir -p docs/process/tickets
  printf '%s\n' "$payload" > "$prompt_file"
  short="Read docs/process/tickets/.ralph-run.md from the workspace root and follow the Instructions section. The issue index and recent commits are in that file; open ticket files from disk."

  if [ "$RALPH_AGENT" = claude ]; then
    ralph_run_claude "$short"
  else
    ralph_run_cursor "$short"
  fi
}

# Claude Code, unattended (no permission prompts, as Cursor's --force). Without an API key
# in its environment it bills the subscription it is signed in to; CLAUDECODE is unset so it
# also starts when Ralph itself was started from a Claude Code session.
# RALPH_MODEL picks a model (opus, sonnet, or a full model id); unset, the account's default.
ralph_run_claude() {
  local model=()
  if ! command -v claude >/dev/null 2>&1; then
    echo "claude not found: install Claude Code and sign in (claude, then /login)" >&2
    exit 1
  fi
  [ -z "${RALPH_MODEL:-}" ] || model=(--model "$RALPH_MODEL")
  env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u CLAUDECODE \
    claude -p --dangerously-skip-permissions --output-format stream-json --verbose \
    "${model[@]}" "$1"
}

ralph_run_cursor() {
  local ps_agent="${CURSOR_AGENT:-}"

  if [ -z "$ps_agent" ] && [ -f "${HOME}/AppData/Local/cursor-agent/agent.ps1" ]; then
    ps_agent="${HOME}/AppData/Local/cursor-agent/agent.ps1"
  fi

  if command -v agent >/dev/null 2>&1; then
    agent --print --force --output-format stream-json --stream-partial-output "$1"
  elif [ -n "$ps_agent" ] && [ -f "$ps_agent" ]; then
    powershell.exe -NoProfile -ExecutionPolicy Bypass \
      -File "$ps_agent" \
      --print \
      --force \
      --output-format stream-json \
      --stream-partial-output \
      "$1"
  else
    echo "cursor agent not found: put agent on PATH or set CURSOR_AGENT to agent.ps1" >&2
    exit 1
  fi
}
