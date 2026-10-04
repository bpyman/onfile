#!/usr/bin/env bash
# Land this worktree's commits on the integration branch, one worker at a time.
# Usage (from a worker's worktree): bash docs/process/ralph/integrate.sh <integration-branch> [--answers-change]
#
# Under a lock shared by every worktree of this repository: fetch, rebase onto the latest
# integration branch, run the feedback loops, and push HEAD to it (fast-forward only).
# The answer comparison runs against the integration branch, so it shows what this
# worker's commits change; pass --answers-change only when the ticket means to change
# what the recorded demo answers, and the commit names each change.
# Exit 0: landed. Exit 2: the rebase conflicted; resolve, `git rebase --continue`, and run
# this again. Exit 3: a check failed after the rebase; fix it, commit, and run this again.
set -uo pipefail

# On Windows, PowerShell's `bash` is WSL's, whose git cannot read a Windows checkout's
# worktree links: run again under Git for Windows' bash, from the same directory.
git_bash="/mnt/c/Program Files/Git/bin/bash.exe"
if grep -qi microsoft /proc/version 2>/dev/null && [ -x "$git_bash" ]; then
  exec "$git_bash" -c 'export PATH="/usr/bin:/mingw64/bin:$PATH"; cd "$(cygpath -u "$1")" && shift && exec bash docs/process/ralph/integrate.sh "$@"' \
    _ "$(wslpath -w "$PWD")" "$@"
fi

branch="${1:?usage: integrate.sh <integration-branch> [--answers-change]}"
answers_change="${2:-}"
common=$(git rev-parse --git-common-dir)
lock="$common/ralph-integrate.lock"

acquire() {
  local waited=0
  until mkdir "$lock" 2>/dev/null; do
    # A lock older than an hour belongs to a worker that died holding it.
    if [ -n "$(find "$lock" -maxdepth 0 -mmin +60 2>/dev/null)" ]; then
      echo "integrate: removing a stale lock" >&2
      rmdir "$lock" 2>/dev/null || true
      continue
    fi
    sleep 5
    waited=$((waited + 5))
    if [ "$waited" -ge 3600 ]; then
      echo "integrate: waited an hour for the lock; giving up" >&2
      exit 4
    fi
  done
  trap 'rmdir "$lock" 2>/dev/null || true' EXIT
}

acquire
git fetch -q origin "$branch"
if ! git rebase "origin/$branch"; then
  echo "integrate: CONFLICT rebasing onto origin/$branch. Resolve it, run" \
    "\`git rebase --continue\`, then run docs/process/ralph/integrate.sh $branch again." >&2
  exit 2
fi

failed=""
uv run -q pytest -q -p no:cacheprovider >/dev/null 2>&1 || failed="$failed pytest"
uv run -q ruff check src tests scripts >/dev/null 2>&1 || failed="$failed ruff"
uv run -q mypy >/dev/null 2>&1 || failed="$failed mypy"
if git diff --name-only "origin/$branch..HEAD" | grep -q '^web/'; then
  (
    cd web &&
      npm run -s lint >/dev/null 2>&1 &&
      npx tsc --noEmit >/dev/null 2>&1 &&
      npx vitest run >/dev/null 2>&1 &&
      npm run -s build >/dev/null 2>&1
  ) || failed="$failed web"
fi
answers=$(uv run -q python scripts/compare_answers.py --against "origin/$branch" --show 0 2>&1)
echo "integrate: $(printf '%s\n' "$answers" | grep -m1 'conversations differ' || echo 'answer comparison did not run')"
if ! printf '%s\n' "$answers" | grep -q '^0 of '; then
  if [ "$answers_change" != "--answers-change" ]; then
    failed="$failed answers"
  fi
fi
if [ -n "$failed" ]; then
  echo "integrate: after rebasing onto origin/$branch these failed:$failed." \
    "Fix them, commit, and run docs/process/ralph/integrate.sh $branch again." \
    "(answers: run scripts/compare_answers.py --against origin/$branch to see the differences.)" >&2
  exit 3
fi

if ! git push -q origin "HEAD:$branch"; then
  echo "integrate: push to $branch was refused; run docs/process/ralph/integrate.sh $branch again" >&2
  exit 3
fi
echo "integrate: landed $(git rev-parse --short HEAD) on $branch"
