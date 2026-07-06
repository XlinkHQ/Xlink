---
name: backend-code-quality
description: Professionally fix bugs, optimize performance, and remove dead code from backend codebases using a disciplined, evidence-driven workflow. Use this skill whenever the user asks to clean up, refactor, debug, optimize, harden, or "tidy up" a backend, server, API, service, worker, or any server-side code — including phrases like "fix the bugs", "make it faster", "remove dead code", "clean the codebase", "optimize the backend", "find the memory leak", "kill the N+1 queries", "this endpoint is slow", "why does this crash under load", or "this service is a mess". Trigger even when the user only hints at it (e.g. "something's broken on the server side" or "there's a lot of cruft in here"). Works across languages and frameworks (Node.js/TypeScript, Python, Go, Java/Kotlin, Ruby, PHP, Rust, C#/.NET, etc.). For deep dives, load the reference files in references/.
---

# Backend Code Quality

A disciplined workflow for improving backend code along three axes: **correctness** (bug fixing), **performance** (optimization), and **cleanliness** (dead-code removal and supporting refactors). The objective is to leave the codebase measurably better — provably, not anecdotally — without changing observable behavior except where a bug fix deliberately requires it.

This file is the operating manual. It is intentionally self-contained for the common case. When a task goes deep on one axis, load the matching reference for detailed technique and per-language tooling:

- `references/debugging.md` — scientific debugging, fault localization, `git bisect`, the full bug taxonomy, and writing regression tests.
- `references/performance.md` — measurement-first optimization, flame graphs, the database/I/O/algorithm/memory hierarchy, caching and concurrency.
- `references/dead-code.md` — mark-and-sweep reachability, language-specific dead-code tools, and the safe staged-removal process.
- `references/tooling.md` — a per-language cheat sheet of linters, profilers, analyzers, and test runners.

## The one rule that prevents most disasters

Every change you make falls into exactly one of two categories, and they must never be mixed in a single commit:

1. **Behavior-preserving** — refactors, dead-code removal, performance tuning. The program does the *same observable thing*; it is just cleaner, leaner, or faster. A passing test suite is your proof that behavior was preserved.
2. **Behavior-changing** — bug fixes. The program *intentionally* does something different because the previous behavior was wrong.

A reviewer must be able to look at any diff and immediately know which kind it is. Mixing a "while I was in here" refactor into a bug fix hides the fix inside noise and is the most common way regressions slip through review. When you genuinely cannot tell whether something is a bug or load-bearing behavior, **stop and ask the user** before changing it — what looks like a defect is sometimes relied upon downstream.

## Workflow

These phases are ordered deliberately. The single most common cause of introduced regressions is acting before understanding, so do not collapse Phase 1.

### Phase 1 — Establish ground truth before touching anything

1. **Identify the stack.** Language, framework, runtime/version, package manager, and the exact commands to build, run, lint, and test. Read the README, the CI config, and the dependency manifest rather than guessing.
2. **Run the existing test suite and record the result.** This passing/failing baseline is the safety net for every behavior-preserving change that follows. Capture the numbers (e.g. "412 passing, 3 failing, 7 skipped") so you can prove at the end that you did not break anything.
3. **If there are no tests, say so explicitly** and treat every change as higher risk. For any critical path you are about to refactor, write a *characterization test* first — a test that simply pins down what the code currently does (correct or not), so a later refactor can be verified as behavior-preserving. See `references/debugging.md`.
4. **Map the entry points and data lifecycle.** HTTP routes, message/queue consumers, scheduled jobs, CLI commands, webhooks, startup hooks. You cannot judge a single function in isolation; understand how a request or message flows through the system first. This map is also what protects you from deleting code that is reached through non-obvious means (reflection, DI, framework auto-discovery).
5. **Skim recent history** (`git log`, blame on the suspect area). Knowing what changed recently is often the fastest route to both a bug's origin and an understanding of why odd-looking code exists.

### Phase 2 — Triage and prioritize by impact × risk

Produce a short, prioritized findings list before doing large work. Tag each item with a category and a severity, and note the risk of the fix itself. Example:

```
Findings (in suggested order):
1. [BUG · high · low-risk]   Unhandled promise rejection in POST /orders can crash the worker process
2. [PERF · high · med-risk]  N+1 query in getUserDashboard — 1 + N round-trips per request (N≈page size)
3. [BUG · med · low-risk]    Cache write is check-then-act; concurrent requests can lose an update
4. [DEAD · low · low-risk]   utils/legacyFormatter.ts — no references found, candidate for deletion
5. [REFACTOR · low · low-risk] 180-line handler in billing.ts mixes parsing, validation, and persistence
```

For a large or ambiguous scope, present this list and let the user steer — they know which subsystems are sensitive. For small, obviously-safe tasks, just proceed and report what you did. Always lead with the highest impact, lowest risk items; they build trust and a safer base for riskier work.

### Phase 3 — Change in small, independently revertible steps

One logical change per commit. Re-run the relevant tests after each. Sequence the work so that risky changes are isolated and can be reverted without unwinding everything else. Prefer the order: low-risk bug fixes → dead-code removal → behavior-preserving refactors → performance work → riskier bug fixes that need design discussion. This keeps the suite green for as long as possible and makes any regression easy to bisect to a single small change.

## Bug fixing — diagnose the root cause, never patch the symptom

A `try/catch` that swallows an error, a `?.` bolted on to silence a crash, or a retry wrapped around a call that fails deterministically — these hide bugs, they do not fix them. Find *why* the wrong value or failure arises.

Use **scientific debugging** (detailed in `references/debugging.md`): state the symptom precisely, form a *falsifiable* hypothesis about the cause, design the smallest experiment that would confirm or refute it, run it, and refine. A hypothesis like "occasionally returns weird data" is useless because it cannot fail a test; "stale data is returned because the cache is not invalidated within the request that updates the profile" is testable. When a bug is a regression, `git bisect` (optionally automated with `git bisect run <script>`) does a binary search over history to pin the exact offending commit — far faster than reading diffs by hand.

Actively hunt these high-frequency backend bug classes (full taxonomy with examples in `references/debugging.md`):

- **Error handling** — unhandled exceptions/rejections, silently swallowed errors, errors logged but not surfaced or not retried correctly, missing rollback/compensation on partial failure.
- **Concurrency** — race conditions on shared state, non-atomic read-modify-write, check-then-act gaps, missing locks or transactions, double-processing of queue messages, deadlocks, lost updates.
- **Resource lifecycle** — DB connections / file handles / sockets not closed or returned to the pool, listeners never removed, unbounded caches/queues, thread/goroutine leaks.
- **Null & boundary** — null/undefined dereference, off-by-one, empty-collection edge cases, integer overflow, timezone/DST and locale handling.
- **Data integrity & security** — missing input validation, SQL/NoSQL/command injection, mass assignment, broken access control, incorrect transaction boundaries, non-idempotent handlers that corrupt state on retry.
- **API contract** — wrong status codes, inconsistent error shapes, accidental breaking changes to responses, pagination/ordering bugs.

For each fix: (1) reproduce it, ideally as a failing test; (2) state the root cause in one or two sentences; (3) apply the minimal correct fix; (4) show the test passing; (5) consider whether the same class of bug exists elsewhere in the codebase and flag those too.

## Performance optimization — measure first, always

**Profile or reason from concrete evidence before changing anything.** Optimizing from a hunch wastes effort and often trades readability for no measurable gain, which is itself a defect. The canonical failure mode: logs say "slow database query", the team spends days tuning SQL, and the real cost was synchronous PDF generation on the request path. A flame graph would have shown it in seconds. (`references/performance.md` covers profiling and flame-graph reading in depth.)

Key measurement discipline:
- Compare **p50 vs p95/p99**, not just averages — tail latency is where N+1s, lock contention, and cache misses hide.
- When comparing before/after under load, **normalize by requests/sec** so you are not fooled by a change in traffic rather than a change in efficiency.
- Validate a win on the metric that matters (usually the SLO percentile), and confirm you did not just move the bottleneck — a faster p50 with a CPU spike or a deeper queue is not a win.

Attack in this order — biggest, cheapest wins first:

1. **Database** — eliminate N+1 queries via batching/eager loading, add missing indexes (verify with the query planner), select only needed columns, paginate instead of loading whole tables, push filtering/aggregation into the query, use prepared statements where the pooler allows.
2. **I/O & network** — parallelize independent async calls, batch external API calls, add caching with *explicit* invalidation, move slow non-essential work (emails, PDFs, thumbnails) off the request path into a background job, avoid blocking the event loop / main thread.
3. **Algorithms & data structures** — replace O(n²) hot loops, pick the right structure (set/map membership vs. repeated linear scans), stream large payloads instead of buffering them entirely in memory.
4. **Allocation & memory** — avoid needless copies, reuse buffers, bound caches, and fix the leaks surfaced during bug hunting.

State the expected impact concretely ("turns 1 + N queries into 2") and re-verify correctness: an "optimization" that changes results is a bug.

## Dead-code removal — only delete what is *provably* unreachable

Dead code is anything provably unused: unreferenced functions/classes/modules, unused imports/variables/parameters, unreachable branches, commented-out blocks, flags for shipped-or-abandoned features, and orphaned files. Removing it measurably helps — teams that detect and prune dead code regularly report meaningfully smaller bundles and faster onboarding — but the word that matters is **provably**.

Backends are full of non-obvious entry points. Before deleting, confirm the symbol is not reached via reflection or dynamic dispatch (`getattr`, `obj[name]`, service containers), framework conventions (route auto-discovery, decorators, naming-based handlers, migration runners), public API exports consumed by other repos, tests, build scripts, config, serialization schemas, or another language/service in a polyglot system.

Lean on real tooling rather than eyeballing — modern detectors build a reachability graph (mark-and-sweep) instead of grepping, and many attach a confidence score (`references/dead-code.md` and `references/tooling.md` have the per-language list). Note that for JS/TS, **knip is the current recommendation; ts-prune is in maintenance mode**. Python uses `vulture` (with a confidence threshold), Go has `deadcode` and `staticcheck`, C# has Roslyn analyzers, and so on. Static tools cannot see code made dead only at runtime (a branch whose condition never holds), so combine static analysis with coverage data when it matters.

Process: search the whole repo for every reference → run the language's dead-code tool → remove in a **separate, behavior-preserving commit** → run the full suite → start with one category (unused exports *or* unused files, not everything at once) so the review stays small and any mistake is easy to revert. When you are not certain something is dead, **list it as a candidate and ask** rather than deleting it. Never delete code merely because it looks unfamiliar — not understanding it is a reason to investigate, not to remove.

## Supporting refactors

Behavior-preserving improvements that make the codebase healthier and the above work safer: extract duplicated logic, name things clearly, shrink giant functions, flatten deep nesting with early returns, replace magic numbers with named constants, and tighten types. Keep each refactor small and test-backed, and **match the codebase's existing conventions** rather than imposing a personal style. If you find yourself wanting a large architectural change, propose it to the user separately rather than smuggling it in.

## Output and reporting

When you finish a task or a batch, give a summary the user can scan in seconds:

```
## Summary
Bugs fixed:        <count>  (root cause, one line each)
Perf improvements: <count>  (with measured or expected impact)
Dead code removed: <count>  (files/symbols, LOC removed)
Refactors:         <count>

## Tests
Before: X passing / Y failing
After:  Z passing / 0 failing

## Needs your decision
- <anything ambiguous: behavior that might be intentional, risky deletions, fixes that imply a design change>
```

Be honest about uncertainty. If you could not run the tests, say so plainly. If a "fix" is a judgment call, surface it rather than burying it. A clear, trustworthy report — including the things you deliberately did *not* touch and why — is part of the deliverable.
