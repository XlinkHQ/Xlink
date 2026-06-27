#!/usr/bin/env bash
# Dead-code finder/remover for the XLink web frontend.
#
#   ./scripts/dead-code.sh            # report only (safe, default)
#   ./scripts/dead-code.sh --apply    # actually delete unused files + exports
#
# Uses knip to find: unused files, unused exports/types, unused deps.
# --apply runs `knip --fix` (removes unused exports + empty files), then
# prunes any now-unused imports and re-checks the type build. Nothing is
# committed — review `git diff` afterwards.
set -euo pipefail

cd "$(dirname "$0")/.."

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

echo "▶ scanning for dead code (knip)…"
if [[ $APPLY -eq 0 ]]; then
  npx -y knip@5 --no-progress || true
  echo
  echo "Report only. Re-run with --apply to delete unused files + exports."
  exit 0
fi

echo "▶ APPLY mode — removing unused files, exports and types…"
# --fix: strip unused exports/types and delete files that become empty.
# --allow-remove-files: let knip delete fully-unused files too.
npx -y knip@5 --no-progress --fix --allow-remove-files || true

echo "▶ type-checking after removal…"
rm -rf .next/types
if npx tsc --noEmit; then
  echo "✓ type check passed"
else
  echo "✗ type check FAILED — review changes, knip may have removed something still referenced."
  echo "  Inspect with: git diff   |   undo with: git checkout -- ."
  exit 1
fi

echo
echo "✓ done. Review the diff before committing:"
echo "    git diff --stat"
