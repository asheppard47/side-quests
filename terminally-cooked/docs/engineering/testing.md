---
version: "1.0.0"
schema_version: 2
title: "Testing"
doc_type: detail
parent: docs/engineering/INDEX.md
last_updated: 2026-11-01
last_audit: 2026-08-19
audit_status: needs-review
domain: docs
triggers:
  - "llm grader tests"
  - "run tests"
  - "test suite"
---
# Testing

**Ninety-two tests run against synthetic transcripts built in-test, covering sequence bookkeeping, privacy, supported harness adapters, auto-pick safeguards, output-file safety, and the PNG renderer.** No test depends on a real session file, so the suite is deterministic and safe to run anywhere.

```bash
python3 test_grade_session.py     # 101 tests, self-reporting, exit 1 on failure
```

## What is covered

| Area | Tests |
|---|---|
| Counting and tallies | basic green/red/streak accounting, test-tally pair extraction, failures-first / semicolon / failure-only summaries, tie-break by suite size, test-runner command recognition (reads, echoes and compound commands rejected, output-filter pipelines accepted only with allowlisted options, input redirection rejected, quoted operators respected) |
| Doom loop | trigger at three identical failures, non-trigger on different commands, reset by an intervening success |
| Cook chain | trigger at 50 consecutive green calls, reset by an error, no growth across a human turn |
| Clean windows | chain built from timestamps, broken by an error, reset by two sparse windows, a window completed by a later non-tool timestamp, a deduplicated Gemini repeat or a Codex final message; timing records never change counts |
| Compaction | the verified `isCompactSummary` marker |
| Permission modes | bypass-permissions detection |
| Token accounting | usage summation including cache fields |
| Scoring math | superlinear streak growth, streak cap, chain product cap, flavor adds without multiplying, debuffs biting chains, superlinear window chain, score floor |
| Provenance | transcript hash changes with content and appears in the card; code hash covers both modules; Grok hash covers compaction checkpoints; Night Shift zone is explicit and stamped |
| Safety | card allowlist leak test, metadata injection sanitisation, model and effort allowlists, filename-derived ids, allowlisted tool labels, ANSI/HTML/path payloads across terminal, HTML, caption and default filename, untrusted dates |
| Adapters | per-harness fixtures; non-object records skipped (including discovery); Codex envelope outcomes, one human per turn, `apply_patch` not a command; Gemini per-message snapshots; Claude compaction and system-reminder records not human; Codex known context markers only (an XML-prefixed prompt is human); valid JSON with wrong-typed discriminators or ids skipped; Grok tool output text |
| Selection | invoker excluded by id; explicit targets matching the invoker refused, including symlink aliases and renamed copies under any extension (transcript ids); heuristic exclusion over the unfiltered list; stale same-project transcripts cannot shield the live one; analysis cap covers today |
| Output and PNG | source-file, existing-file and symlink destinations refused without `--force`; no-force publication fails closed without hard links; `--png`/`--html` refuse a non-card extension; network-off Chrome flags and CSP; waits for a complete PNG; truncated or corrupt PNGs are a clean error |
| CLI | end-to-end smoke run |

## The two tests that matter most

**`test_html_card_allowlist`** plants secret prompt text, tool output and a filesystem path into a fixture, renders the HTML card, and asserts none of them appear. This is the executable form of the privacy contract; it should fail loudly if anyone widens what the card prints.

**`test_meta_injection_sanitized`** puts a script tag inside a model name — a transcript-controlled field — and asserts the rendered card contains no live markup. Found by external review, not by the author.

## Conventions

- Fixtures are constructed with small helpers (`prompt`, `asst`, `tool_use`, `result`) and written to temporary files; no real transcripts are read.
- Sequence tests always assert a near-miss as well as a hit, because thresholds without a negative case are how a detector quietly fires on everything.
- Scoring tests use a minimal stats dict rather than a transcript, so formula changes are isolated from parsing changes.
- Tests that depend on local time zones assert on class-filtered modifiers or pass an explicit `tz` to stay deterministic.
- PNG tests drive the CLI with a fake `CHROME_BIN` shell script, so they run without Chrome and can record the launch flags; one optional test uses real Chrome when it is installed.
- The runner counts any exception, not only a failed assert, as a failure and keeps going.

## Gates before shipping a change

1. The suite passes.
2. A smoke run over a spread of real local sessions shows no modifier firing on nearly everything or on nothing.
3. Any change to what the card prints is accompanied by an updated allowlist test.
4. Any scoring change bumps the scoring version, because old cards must remain interpretable.
