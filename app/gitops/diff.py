from __future__ import annotations

from typing import Any

from app.gitops.models import GitDiff


class DiffEngine:
    def compare(self, before: dict[str, Any], after: dict[str, Any]) -> GitDiff:
        before_keys = set(before)
        after_keys = set(after)
        added = {key: after[key] for key in sorted(after_keys - before_keys)}
        removed = {key: before[key] for key in sorted(before_keys - after_keys)}
        changed = {
            key: {"before": before[key], "after": after[key]}
            for key in sorted(before_keys & after_keys)
            if before[key] != after[key]
        }
        return GitDiff(added=added, changed=changed, removed=removed)

    def reverse(self, diff: GitDiff) -> GitDiff:
        return GitDiff(
            added=diff.removed,
            changed={
                key: {"before": value["after"], "after": value["before"]}
                for key, value in diff.changed.items()
            },
            removed=diff.added,
        )
