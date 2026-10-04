#!/usr/bin/env bash
# Ralph with several workers at once, each in its own worktree.
# Usage: bash docs/process/ralph/afk-parallel.sh <workers> <max-tickets> <integration-branch> [feature-slug]
#        RALPH_TICKETS="07 12" ... limits the run to those ticket numbers.
#
# The integration branch must exist on origin. Workers land their work on it; nothing
# lands on master, which takes the branch through a pull request as usual.
# - Worker k works in ../<repo>-w<k> on branch ralph-w<k>, reset to the integration branch
#   before each ticket (created, with its own .venv and web/node_modules, on first use).
# - The script, not the agent, picks tickets, reading them from the integration branch on
#   origin: under a lock, each free worker gets the lowest actionable ticket no other worker
#   holds (Status ready-for-agent, What to build present, every Blocked by ticket resolved
#   or in issues/done/). A ticket blocked by one still in progress waits until that lands.
# - Agents close their ticket in the commit that does the work, then land it with
#   docs/process/ralph/integrate.sh (rebase, checks, answer comparison, push), one at a time.
# - A ticket still open after its run (unfinished) may be taken up again, at most
#   $RALPH_MAX_ATTEMPTS times per run (default 2), then waits for the next run.
# It stops after <max-tickets> distinct tickets (a retry of one doesn't count again), when
# nothing is left to do, or a worker's agent fails.
set -eo pipefail

# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
ralph_cd_root

workers="${1:-}"
max_tickets="${2:-}"
integration="${3:-}"
feature="${4:-}"
only="${RALPH_TICKETS:-}"
max_attempts="${RALPH_MAX_ATTEMPTS:-2}"
if ! [[ "$workers" =~ ^[1-9][0-9]*$ && "$max_tickets" =~ ^[1-9][0-9]*$ && -n "$integration" ]]; then
  echo "Usage: $0 <workers> <max-tickets> <integration-branch> [feature-slug]"
  exit 1
fi

root=$(pwd)
repo=$(basename "$root")
git fetch -q origin "$integration" || {
  echo "Branch $integration is not on origin; push it with -u first" >&2
  exit 1
}
common=$(cd "$(git rev-parse --git-common-dir)" && pwd)
state="$common/ralph-parallel"
logs="$root/.cache/ralph"
rm -rf "$state"
mkdir -p "$state/claims" "$state/attempts" "$logs"
echo 0 > "$state/started"

lock() {
  until mkdir "$state/lock" 2>/dev/null; do sleep 1; done
}
unlock() {
  rmdir "$state/lock" 2>/dev/null || true
}

# A ticket file's Status, from the integration branch on origin.
ticket_status() {
  git show "origin/$integration:$1" 2>/dev/null |
    grep -m1 -E '^\*\*Status:\*\*|^Status:' | sed -E 's/^\*\*Status:\*\* *|^Status: *//' || true
}

# Whether ticket NN of a feature is finished: resolved/done, or moved to issues/done/.
ticket_finished() {
  local dir="$1" number="$2" file status
  if git ls-tree -r --name-only "origin/$integration" "$dir/done" 2>/dev/null | grep -q "/${number}-[^/]*\.md$"; then
    return 0
  fi
  file=$(git ls-tree --name-only "origin/$integration" "$dir/" | grep "/${number}-[^/]*\.md$" | head -n 1)
  [ -n "$file" ] || return 1
  status=$(ticket_status "$file")
  [[ "$status" == resolved* || "$status" == done* ]]
}

# Open ready-for-agent tickets with every blocker finished, lowest first, as paths.
actionable() {
  git fetch -q origin "$integration"
  local dirs dir file name number status body blockers blocker
  if [ -n "$feature" ]; then
    dirs="docs/process/tickets/$feature/issues"
  else
    dirs=$(git ls-tree -d -r --name-only "origin/$integration" docs/process/tickets | grep '/issues$' || true)
  fi
  for dir in $dirs; do
    for file in $(git ls-tree --name-only "origin/$integration" "$dir/" | grep -E '/[0-9]{2}-[^/]*\.md$' | sort); do
      name=$(basename "$file")
      number="${name:0:2}"
      if [ -n "$only" ] && [[ " $only " != *" $number "* ]]; then
        continue
      fi
      status=$(ticket_status "$file")
      [[ "$status" == ready-for-agent* || -z "$status" ]] || continue
      body=$(git show "origin/$integration:$file")
      grep -q '^\*\*What to build:\*\*' <<<"$body" || continue
      blockers=$(grep -m1 -E '^\*\*Blocked by:\*\*|^Blocked by:' <<<"$body" | grep -oE '\b[0-9]{2}\b' || true)
      for blocker in $blockers; do
        ticket_finished "$dir" "$blocker" || continue 2
      done
      echo "$file"
    done
  done
}

# Claim the next ticket for worker $1: prints its path, or nothing.
claim_next() {
  local worker="$1" started candidates file key tries
  candidates=$(actionable) || return 0
  lock
  started=$(cat "$state/started")
  for file in $candidates; do
    key=$(echo "$file" | tr '/' '_')
    tries=$(cat "$state/attempts/$key" 2>/dev/null || echo 0)
    # Taken by another worker, or tried enough this run.
    if [ -e "$state/claims/$key" ] || [ "$tries" -ge "$max_attempts" ]; then
      continue
    fi
    # A new ticket needs room in the budget; a retry of one already started does not.
    if [ "$tries" -eq 0 ] && [ "$started" -ge "$max_tickets" ]; then
      continue
    fi
    echo $((tries + 1)) > "$state/attempts/$key"
    echo "$worker" > "$state/claims/$key"
    [ "$tries" -eq 0 ] && echo $((started + 1)) > "$state/started"
    echo "$file"
    break
  done
  unlock
}

release() {
  rm -f "$state/claims/$(echo "$1" | tr '/' '_')"
}

ensure_worktree() {
  local k="$1" wt="$2"
  if [ ! -d "$wt" ]; then
    git worktree add -q -B "ralph-w$k" "$wt" "origin/$integration"
    (cd "$wt" && uv sync -q && { [ ! -f web/package.json ] || (cd web && npm ci --silent); })
  fi
}

# Cursor's stream: the agent's new text, without its duplicate flush events (as afk.sh).
stream_text='
  select(
    .type == "assistant"
    and has("timestamp_ms")
    and (has("model_call_id") | not)
  )
  | .message.content[]?
  | select(.type == "text")
  | .text // empty
'

rules() {
  local k="$1" ticket="$2"
  cat <<EOF
# PARALLEL RUN: these rules come first and override the ones below

You are worker $k of a parallel Ralph run. Other workers may be working other tickets, in
other worktrees, at the same time; all of you land your work on the branch \`$integration\`.

- Your ticket is \`$ticket\`. It was chosen for you, so skip the ISSUES selection below and
  work on it only. If it turns out not to be actionable (resolved, blocked, or a spec),
  change nothing and say why.
- CLOSE THE TICKET in the same commit as the work: set its Status, append its \`## Answer\`,
  and append your entry to \`docs/process/progress.txt\`, so the ticket closes as the work lands.
- COMMIT on your current branch as described below, but instead of stopping there, run
  \`bash docs/process/ralph/integrate.sh $integration\` (add \`--answers-change\` only if
  your ticket means to change what the recorded demo answers, and your commit names each
  change). It rebases your commits onto the latest \`$integration\`, runs the feedback loops
  and the answer comparison, and pushes. Exit 2 means the rebase conflicted: resolve it,
  keeping both sides' intent, run \`git rebase --continue\`, then run it again. Exit 3 means a
  check failed after the rebase: fix it, commit, and run it again.
- Run integrate.sh in the foreground and wait for it to finish (it can take a few minutes:
  it waits its turn, then runs every check). Never start it in the background: your
  session ends when you stop, and work never seen landing does not count.
- Finish by quoting the commit hash integrate.sh printed after "landed".
- This push to \`$integration\` is the one push the LIMITS below allow. Never push anywhere
  else, never touch another worktree, and never force-push.

EOF
}

work() {
  local k="$1" wt="$root/../$repo-w$k" log="$logs/ralph-w$k.log" ticket tmp status
  ensure_worktree "$k" "$wt"
  while true; do
    ticket=$(claim_next "$k")
    if [ -z "$ticket" ]; then
      # Nothing free now; wait while another worker's ticket may still unblock one.
      if [ -z "$(ls -A "$state/claims")" ]; then # nobody else holds one that may unblock more
        echo "[w$k] nothing left to do" | tee -a "$log"
        return 0
      fi
      sleep 60
      continue
    fi
    echo "[w$k] $ticket: starting $(date '+%H:%M')" | tee -a "$log"
    tmp=$(mktemp)
    status=0
    (
      cd "$wt"
      git fetch -q origin "$integration"
      # Start clean: whatever an earlier agent left here unfinished is dropped (its ticket
      # stays open for the next one); ignored files (.venv, node_modules, .cache) stay.
      git checkout -q -f -B "ralph-w$k" "origin/$integration"
      git clean -fdq
      ralph_run_agent "Previous commits:

$(ralph_recent_commits)

Instructions:

$(rules "$k" "$ticket")
$(cat docs/process/ralph/prompt.md)"
    ) | tee "$tmp" | jq --unbuffered -rj "$stream_text" >> "$log" 2>&1 || status=$?
    release "$ticket"
    if [ "$status" -ne 0 ] || ! jq -e 'select(.type == "result" and .subtype == "success")' "$tmp" >/dev/null 2>&1; then
      echo "[w$k] $ticket: the agent failed ($(jq -r 'select(.type == "result") | .result // .subtype' "$tmp" 2>/dev/null | tail -n 1)); worker stops" | tee -a "$log"
      rm -f "$tmp"
      return 1
    fi
    rm -f "$tmp"
    echo "[w$k] $ticket: done $(date '+%H:%M')" | tee -a "$log"
  done
}

echo "Parallel Ralph: $workers workers, up to $max_tickets tickets, landing on $integration"
pids=()
for ((k = 1; k <= workers; k++)); do
  work "$k" &
  pids+=("$!")
  sleep 20 # stagger, so the first ones claim before the rest look
done
failed=0
for pid in "${pids[@]}"; do
  wait "$pid" || failed=1
done
echo "Parallel Ralph finished: $(cat "$state/started") tickets started; logs in .cache/ralph/ralph-w*.log"
exit "$failed"
