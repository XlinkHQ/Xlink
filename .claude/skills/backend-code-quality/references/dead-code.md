# Dead Code Reference

Detailed technique for the cleanliness axis. Removing dead code is worthwhile — teams that prune it regularly report meaningfully smaller bundles/builds and faster onboarding — but every deletion is a behavior-preserving change that must be *proven* safe.

## What counts as dead code

- Unreferenced functions, classes, methods, modules, and whole files.
- Unused imports, variables, parameters, and struct/enum fields.
- Unreachable branches (code after an unconditional return/throw; conditions that can never be true).
- Commented-out blocks left "just in case."
- Feature flags and their guarded code for features that shipped permanently or were abandoned.
- Dependencies in the manifest that nothing imports (also a security/maintenance cost).

## Mark-and-sweep beats grep

Old tools grepped for a name and guessed. Modern detectors build a **reachability graph** from real entry points and mark everything reachable; whatever is left unmarked is dead. This catches mutually-recursive dead code (two unused functions that only call each other — grep would see "references" and miss it) and avoids false hits from same-named symbols. Good tools also attach a **confidence score or reason**, so you can sort obvious wins from risky guesses.

Static analysis has a hard limit: it cannot see code that is dead only at **runtime** (a branch whose guard never holds, a loop that never runs). For those, combine static results with **coverage data** from the test suite or production tracing.

## The non-obvious entry points that make naive deletion dangerous

Before deleting, prove the symbol is not reached via any of these:

- **Reflection / dynamic dispatch / string-keyed lookup** — `getattr`, `obj[name]`, `Class.forName`, dependency-injection containers, service registries.
- **Framework conventions** — route/handler auto-discovery, decorators/annotations, naming-based wiring, migration runners, scheduled-task registration.
- **Public API surface** — exports consumed by *other* repositories or published packages. A single-repo scan can't see these; check downstream consumers.
- **Tests, build scripts, config, and serialization** — a field may exist only to match a stored/serialized schema or wire format even if no code reads it directly.
- **Other languages/services** in a polyglot system — an endpoint or symbol called over the network or FFI.

When in doubt about any of these, **list the symbol as a candidate for removal and ask the user** instead of deleting. Never delete code just because it's unfamiliar; not understanding it is a reason to investigate.

## Safe staged-removal process

1. **Scope to one category at a time** — unused exports *or* unused files *or* unused deps — not everything at once. Small reviews catch mistakes.
2. **Run the language's dead-code tool** (table below) and, for runtime-dead code, cross-reference coverage.
3. **Confirm reachability** against the non-obvious entry points above (the tool's plugins handle many framework cases, but verify public API and cross-service use yourself).
4. **Delete in a separate, behavior-preserving commit** with a message that says what was removed and how you verified it's unused.
5. **Run the full test suite** after removal.
6. **Keep patches small** so any over-eager deletion is trivial to revert and any CI failure is obvious.

## Per-language dead-code tools

| Language | Primary tool(s) | Notes |
|---|---|---|
| JavaScript / TypeScript | **knip** (recommended) | Mark-and-sweep; finds unused files, exports, types, and dependencies. Plugin system auto-detects React/Next/Vite, Jest/Vitest, etc. `--reporter json`, `--workspace`, `--changed`, `--max-issues` for CI gating. |
| JavaScript / TypeScript | ts-prune | **Maintenance mode** — prefer knip. Couldn't detect unused deps or mutually-recursive dead code. |
| JavaScript / TypeScript | eslint-plugin-unused-imports, depcheck | Unused imports (auto-fix) and unused dependencies respectively; knip subsumes much of this. |
| Python | **vulture** | Unused functions/classes/vars; tune `--min-confidence` (e.g. 60) to balance false positives. Pair with coverage for runtime-dead code. |
| Python | pyflakes / ruff (F-codes), pylint | Unused imports/locals; ruff is fast and good in CI. |
| Go | **deadcode** (golang.org/x/tools), staticcheck (U-checks) | Reachability-based; integrates with `go vet`-style workflows. |
| Java / Kotlin | IntelliJ inspections, Error Prone, detekt (Kotlin) | IDE "find usages" + analyzers; beware reflection/DI false negatives. |
| C# / .NET | Roslyn analyzers, IDE0051/IDE0052, tools like DeadSharp | Roslyn-based unused-member detection. |
| PHP | tooling that hooks the autoloader to find unreferenced classes; Psalm/PHPStan dead-code rules | Confirm against framework auto-wiring. |
| Ruby | debride, RuboCop (Lint/Useless*), coverage | Heavy reflection/metaprogramming makes static results lower-confidence; lean on coverage. |
| Rust | compiler `dead_code` lint (warn by default), clippy | The compiler already flags most unused items; `#[allow(dead_code)]` markers are a signal to investigate. |

For multi-language repos or when you need ownership/history context before touching a shared module, graph-based analyzers that combine the call graph with git history help separate genuinely dead debris from old-but-load-bearing infrastructure.
