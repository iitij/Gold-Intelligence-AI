#!/usr/bin/env bash
# Inspect this existing private repository; NO force-push, no destructive updates.
set -euo pipefail
TARGET='iitij/Gold-Intelligence-AI'
if [[ $# -gt 0 && "$1" != "$TARGET" ]]; then
  echo 'Unexpected target; refusing' >&2; exit 2
fi
command -v gh >/dev/null || { echo 'Install GitHub CLI (gh)' >&2; exit 2; }
command -v git >/dev/null || { echo 'Install Git' >&2; exit 2; }
OWNER="$(gh api user --jq .login)"
[[ "$OWNER" == 'iitij' ]] || { echo 'Authenticated owner mismatch' >&2; exit 2; }
PRIVATE="$(gh repo view "$TARGET" --json isPrivate --jq .isPrivate)"
[[ "$PRIVATE" == 'true' ]] || { echo 'Repository must be private' >&2; exit 2; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 scripts/check_repository_policy.py
python3 scripts/publish_issues.py --repo "$TARGET" --dry-run
echo 'Repo is ready for normal pull-request development:'
echo "https://github.com/$TARGET"
echo 'Never automatically overwrite existing main.'
