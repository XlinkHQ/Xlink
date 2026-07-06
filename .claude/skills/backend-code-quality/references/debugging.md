# Debugging Reference

Detailed technique for the bug-fixing axis. Load this when a bug is non-trivial — intermittent, a regression, a crash under load, or one where the distance between the symptom and the root cause is large (research shows that distance is exactly what makes bugs hard and time-consuming).

## Scientific debugging

Treat a bug like a scientific investigation rather than a guessing game. The loop:

1. **Observe and define the problem precisely.** Capture the exact symptom, the environment, and whether it is deterministic or intermittent. Identify known triggers. A vague problem statement ("sometimes it shows weird data") cannot drive an investigation; a precise one ("users see the previous profile photo for ~30s after updating it, only on cache hits") can.
2. **Formulate a falsifiable hypothesis.** State a testable explanation of the root cause. Falsifiable means it can be proven *wrong*. Not falsifiable: "occasionally the app misbehaves." Falsifiable: "stale data is served because the cache entry is not invalidated in the same request that updates the profile."
3. **Predict and design the smallest experiment.** If the hypothesis is true, what should a specific test, log line, or debugger inspection show? Design the cheapest experiment that would distinguish "true" from "false."
4. **Run it and observe the actual result.**
5. **Confirm or reject, then refine.** Repeat until the cause is pinned. Each cycle should eliminate a chunk of the search space, not just add noise.

This is the same mark-the-hypothesis-and-test discipline that tools automate; doing it explicitly keeps you from the common trap of "fixing" things that were never the cause.

## Fault localization: forward vs. backward tracing

- **Backward tracing ("drill up from the problem to the bug")** — start at the observed failure and work backwards through the data and control flow to the cause. Use when the failure has an identifiable, reproducible symptom. Most practitioners start here, navigating at the module/file level first, then narrowing.
- **Forward tracing ("drill down from program start to the bug")** — follow execution from an entry point forward. Use when the failure is diffuse or hard to pin to a single symptom.

Pick the mode based on how identifiable the cause is, and switch as your understanding of the abstraction level changes.

## git bisect — binary search over history for regressions

When something worked before and is broken now, `git bisect` finds the offending commit in O(log n) steps instead of reading every diff.

```bash
git bisect start
git bisect bad                 # current commit is broken
git bisect good <known-good>   # e.g. a release tag that worked
# git checks out a midpoint; test it, then mark good/bad:
git bisect good   # or: git bisect bad
# ...repeat until git names the first bad commit
git bisect reset
```

Automate it when you have a script that exits 0 for "good" and non-zero for "bad":

```bash
git bisect start <bad> <good>
git bisect run ./scripts/repro_test.sh
```

This is delta debugging applied to version history: each step halves the solution space. Once the commit is found, read its (ideally small) diff to understand the root cause — another reason to keep commits small in the first place.

## Reproduction and regression tests

A bug you cannot reproduce is a bug you cannot confirm you fixed. The ideal artifact is a **failing test that captures the bug**: it documents the defect, proves the fix works when it goes green, and prevents the bug from silently returning. Write it before the fix where feasible.

When refactoring code that has no tests, write a **characterization test** first: assert the *current* behavior (even if imperfect) so that a behavior-preserving refactor can be verified. If the characterization test later needs to change, that change is itself a behavior change and belongs in its own commit.

## Bug taxonomy with concrete tells

**Error handling**
- Empty or log-only `catch` blocks that let execution continue in a bad state.
- Promises/futures not awaited; rejections with no handler (can crash the process in Node).
- No rollback/compensation when a multi-step operation fails partway.
- Retrying a deterministically-failing call forever.

**Concurrency**
- Read-modify-write that is not atomic (`x = get(); set(x + 1)`), losing updates under concurrency.
- Check-then-act: `if (!exists(k)) create(k)` racing another request doing the same.
- Shared mutable state without a lock; mutating a cache while others read it.
- Queue consumers that process a message more than once because ack happens before the work commits.
- Lock ordering inconsistencies → deadlock.

**Resource lifecycle**
- Connections/handles/sockets acquired but not released on the error path (use the language's `with`/`defer`/`try-with-resources`/`using`).
- Event listeners or subscriptions added per request and never removed.
- Unbounded caches, queues, or in-memory accumulators that grow until OOM.

**Null & boundary**
- Dereferencing a value that can be null/undefined; assuming a collection is non-empty.
- Off-by-one in slicing/pagination; inclusive vs. exclusive bounds.
- Integer overflow; float used for money; timezone/DST and locale mistakes.

**Data integrity & security**
- Unvalidated input reaching a query or shell (SQL/NoSQL/command injection) — use parameterized queries.
- Mass assignment binding fields the user should not control.
- Missing authorization checks (broken access control).
- Non-idempotent handlers that corrupt state when a client retries — add idempotency keys.

**API contract**
- Wrong/inconsistent status codes and error shapes.
- Silent breaking changes to response structure.
- Pagination that drops or duplicates rows when data changes between pages.

For each, after fixing, grep the codebase for the same pattern — bug classes cluster.
