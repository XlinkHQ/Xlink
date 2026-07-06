# Tooling Cheat Sheet

Per-language tools for the three axes. Use the ones that match the repo's stack; confirm a tool is installed/configured before relying on it, and prefer tools the project already uses (check CI config and dev dependencies).

## JavaScript / TypeScript (Node)
- **Test/coverage:** vitest, jest; coverage via c8 / built-in.
- **Lint/static:** ESLint (+ typescript-eslint), `tsc --noUnusedLocals --noUnusedParameters`.
- **Dead code:** **knip** (files, exports, types, deps), eslint-plugin-unused-imports, depcheck. (ts-prune = maintenance mode.)
- **Profiling:** `node --prof` + `--prof-process`, clinic.js, 0x (flame graphs), Chrome DevTools inspector, `--cpu-prof`.
- **DB/N+1:** ORM query logging (Prisma `log: ['query']`, Sequelize/TypeORM logging), APM.

## Python
- **Test/coverage:** pytest, coverage.py / pytest-cov.
- **Lint/static:** ruff (fast, F-codes for unused), pyflakes, pylint, mypy/pyright.
- **Dead code:** **vulture** (`--min-confidence`), ruff/pyflakes for imports.
- **Profiling:** cProfile + snakeviz, py-spy (sampling, no code change, prod-safe, can emit flame graphs), scalene (CPU+memory), line_profiler, memray (memory).
- **DB/N+1:** Django Debug Toolbar / `nplusone`, SQLAlchemy echo, query-count assertions in tests.

## Go
- **Test/coverage:** `go test -cover`, `-race` for the data-race detector.
- **Lint/static:** `go vet`, staticcheck, golangci-lint, `deadcode`.
- **Profiling:** built-in `pprof` (CPU/heap/block/mutex), `go test -bench` + benchstat, flame graphs via pprof.
- **DB/N+1:** query logging in the driver/ORM, pprof on the handler.

## Java / Kotlin (JVM)
- **Test/coverage:** JUnit, JaCoCo.
- **Lint/static:** Error Prone, SpotBugs, PMD, IntelliJ inspections, detekt/ktlint (Kotlin).
- **Dead code:** IDE "find usages" + inspections, Error Prone; beware reflection/DI.
- **Profiling:** async-profiler (low-overhead, flame graphs), JFR (Java Flight Recorder), VisualVM, YourKit.
- **DB/N+1:** Hibernate statistics / `show_sql`, p6spy, datasource-proxy.

## C# / .NET
- **Test/coverage:** xUnit/NUnit, coverlet.
- **Lint/static:** Roslyn analyzers (IDE0051/0052 unused members), DeadSharp.
- **Profiling:** dotnet-trace, dotnet-counters, PerfView, Visual Studio profiler.
- **DB/N+1:** EF Core logging, MiniProfiler.

## Ruby
- **Test/coverage:** RSpec/Minitest, SimpleCov.
- **Lint/static:** RuboCop, debride; reflection-heavy, so lean on coverage.
- **Profiling:** stackprof (flame graphs), rbspy (sampling, prod-safe), ruby-prof, memory_profiler.
- **DB/N+1:** Bullet gem, `rack-mini-profiler`, ActiveRecord query logs.

## PHP
- **Test/coverage:** PHPUnit, Pest; coverage via Xdebug/PCOV.
- **Lint/static:** PHPStan, Psalm (dead-code rules), autoloader-hooking dead-class finders.
- **Profiling:** Xdebug profiler, XHProf, Blackfire, eBPF agents (pyroscope/parca) for php-fpm in prod.
- **DB/N+1:** Laravel Debugbar / Telescope, query logging.

## Rust
- **Test/coverage:** `cargo test`, cargo-llvm-cov/tarpaulin.
- **Lint/static:** clippy, compiler `dead_code` lint.
- **Profiling:** `cargo flamegraph`, perf, samply; criterion for benchmarks.
- **Memory:** valgrind/heaptrack where applicable.

## Cross-cutting / language-agnostic
- **Flame graphs:** Linux `perf` + Brendan Gregg's FlameGraph; eBPF profilers (parca, pyroscope) for low-overhead production profiling.
- **Regression localization:** `git bisect` / `git bisect run <script>`.
- **APM / distributed tracing:** Datadog, Splunk, OpenTelemetry-based stacks — flame graphs correlated with traces and SLOs.
- **DB:** `EXPLAIN ANALYZE` (or engine equivalent) to verify index usage and planning vs. execution cost.
