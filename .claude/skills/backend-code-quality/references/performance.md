# Performance Reference

Detailed technique for the optimization axis. The governing rule: **measure first, optimize the proven bottleneck, verify the win.** Reasoning about performance from intuition is unreliable; the bottleneck is frequently somewhere other than where the logs or your instinct point.

## Why measurement comes first (a cautionary pattern)

A team's API took ~2s/request. Logs said "database query slow," so they tuned SQL for days with no improvement. A flame graph showed the real cost was synchronous PDF generation on the request path. Moving it to a background job dropped the request to ~300ms. The lesson: a profile would have pointed at the true cost immediately. Never spend effort optimizing a component you have not measured.

## Flame graphs

A flame graph aggregates thousands of sampled stack traces into one picture of where time goes.

- **Width = time.** A frame occupying 60% of the width consumed ~60% of the sampled time. Wide frames near the top are your immediate wins.
- **Height = call-stack depth.** The bottom is the entry point (e.g. the HTTP handler); each layer up is a callee.
- **Plateaus** (wide flat regions near the top) are the cheapest targets. A pattern that repeats across many stacks indicates a broad win; one narrow-but-huge frame suggests a single-route fix.
- **Self time** — time in a function excluding its callees — high self time flags a function worth optimizing directly (but a hot frame can also just be an idle thread, so confirm).

Generating one (sampling profiler → folded stacks → SVG), e.g. with Linux `perf` + Brendan Gregg's FlameGraph:

```bash
perf record -F 99 -a -g -- sleep 30
perf script | ./stackcollapse-perf.pl | ./flamegraph.pl > profile.svg
```

Newer kernels can use eBPF-based profilers (`profile-bpfcc`, parca/pyroscope agents) for lower overhead, suitable for production at low sampling rates. APMs (Datadog, Splunk, etc.) produce flame graphs correlated with distributed traces.

### Reading discipline

- **Compare p50 vs p95/p99 flame graphs.** p50 often shows the happy path (cache hits); p95/p99 reveals cache misses, lock contention, N+1s, and cold paths — which is usually where the SLO pain actually lives.
- **Capture two windows** when chasing a regression: steady state and degraded. The frame that is wide *only* in the degraded window is your suspect.
- **Normalize by req/sec** before comparing before/after, so you measure efficiency, not a traffic change.
- **Differential flame graphs** (red/blue deltas between two profiles) make before/after comparisons obvious.

## The optimization hierarchy (biggest, cheapest wins first)

### 1. Database — usually the largest single win
- **N+1 queries**: the classic. One query for a list, then one per row. Detect it (ORM query logs, APM, or a dev-mode N+1 detector) and fix with eager loading / a `JOIN` / a single batched `WHERE id IN (...)`. Turning `1 + N` into `1` or `2` queries is often a 10–100× latency drop on the path.
- **Missing indexes**: confirm with the query planner (`EXPLAIN ANALYZE`) rather than adding indexes speculatively — each index also costs write time and storage.
- **Over-fetching**: select only the columns you use; avoid `SELECT *`. Don't load an entire table into app memory to filter in code — push the filter/aggregate into SQL.
- **Pagination**: prefer keyset/seek pagination over large `OFFSET` on big tables.
- **Prepared statements / planning overhead**: under some pooler configs (e.g. transaction-mode PgBouncer) clients can't reuse prepared statements, so the DB re-parses and re-plans the same query repeatedly — a real and easily-missed cost. Profiling the DB itself can reveal time spent planning rather than executing.

### 2. I/O and network
- **Parallelize independent awaits** instead of awaiting in series.
- **Batch external calls** rather than calling per item in a loop.
- **Cache with explicit invalidation.** A cache without a correct invalidation story is a stale-data bug waiting to happen. Decide the invalidation rule before adding the cache.
- **Move slow non-essential work off the request path** — emails, PDF/thumbnail generation, third-party syncs — into a background queue.
- **Don't block the event loop / main thread** with CPU-bound work in async runtimes.

### 3. Algorithms and data structures
- Replace O(n²) hot loops; watch for accidental quadratic behavior from nested iteration over the same growing collection.
- Use the right structure: set/map membership checks instead of repeated linear scans; precompute lookups outside loops.
- **Stream** large payloads (files, big result sets) instead of buffering the whole thing in memory.

### 4. Allocation and memory
- Avoid needless copies and re-serialization; reuse buffers where the language rewards it.
- **Bound every cache and queue.** Unbounded growth is both a leak and a latency cliff (GC pressure).
- For compute-bound hot paths (hashing, regex, JSON encode/decode), consider memoization or changing the data shape.

## Validate the win

Don't celebrate a faster p50. Require improvement on the SLO metric (usually p95 or p99), a stable error rate, and capacity headroom (e.g. CPU < ~70%, queue depth below threshold). If p95 improved but CPU spiked or a downstream queue grew, you moved the bottleneck rather than removing it. For risky changes, ship behind a feature flag with a revert toggle and validate on a canary/shadow rollout before full release. Keep the before/after profiles as evidence.
