---
version: "1.0.0"
schema_version: 2
title: "Testing"
doc_type: detail
parent: docs/engineering/INDEX.md
last_updated: 2026-09-12
last_audit: 2026-08-19
audit_status: needs-review
domain: docs
triggers:
  - "llm grader tests"
  - "run tests"
  - "test suite"
---
# Testing

**Fifty-seven tests run against synthetic transcripts built in-test, covering sequence bookkeeping, privacy, supported harness adapters, and auto-pick safeguards.** No test depends on a real session file, so the suite is deterministic and safe to run anywhere.

```bash
python3 test_grade_session.py     # 57 tests, self-reporting, exit 1 on failure
```

## What is covered

| Area | Tests |
|---|---|
| Counting and tallies | basic green/red/streak accounting, test-tally pair extraction |
| Doom loop | trigger at three identical failures, non-trigger on different commands, reset by an intervening success |
| Cook chain | trigger at 50 consecutive green calls, reset by an error, no growth across a human turn |
| Clean windows | chain built from timestamps, broken by an error, reset by two sparse windows |
| Compaction | the verified `isCompactSummary` marker |
| Permission modes | bypass-permissions detection |
| Token accounting | usage summation including cache fields |
| Scoring math | superlinear streak growth, streak cap, chain product cap, flavor adds without multiplying, debuffs biting chains, superlinear window chain, score floor |
| Provenance | transcript hash changes with content and appears in the card |
| Safety | card allowlist leak test, metadata injection sanitisation |
| CLI | end-to-end smoke run |

## The two tests that matter most

**`test_html_card_allowlist`** plants secret prompt text, tool output and a filesystem path into a fixture, renders the HTML card, and asserts none of them appear. This is the executable form of the privacy contract; it should fail loudly if anyone widens what the card prints.

**`test_meta_injection_sanitized`** puts a script tag inside a model name — a transcript-controlled field — and asserts the rendered card contains no live markup. Found by external review, not by the author.

## Conventions

- Fixtures are constructed with small helpers (`prompt`, `asst`, `tool_use`, `result`) and written to temporary files; no real transcripts are read.
- Sequence tests always assert a near-miss as well as a hit, because thresholds without a negative case are how a detector quietly fires on everything.
- Scoring tests use a minimal stats dict rather than a transcript, so formula changes are isolated from parsing changes.
- Tests that depend on local time zones assert on class-filtered modifiers to stay deterministic.

## Gates before shipping a change

1. The suite passes.
2. A smoke run over a spread of real local sessions shows no modifier firing on nearly everything or on nothing.
3. Any change to what the card prints is accompanied by an updated allowlist test.
4. Any scoring change bumps the scoring version, because old cards must remain interpretable.
