---
version: "1.0.0"
schema_version: 2
title: "Transcript Observables"
doc_type: detail
parent: docs/engineering/INDEX.md
last_updated: 2026-09-12
last_audit: 2026-08-19
audit_status: needs-review
domain: docs
triggers:
  - "session jsonl"
  - "transcript format"
  - "isCompactSummary"
  - "what can we detect"
---
# Transcript Observables

**This leaf records Claude Code observables from one local JSONL file per session; every observable listed here was verified against real transcripts rather than assumed.** That distinction is not academic: the first compaction detector shipped against a guessed marker and could never have fired.

Other supported harnesses have different stores and record shapes; see [harness-adapters.md](../design/harness-adapters.md).

## Location

`~/.claude/projects/<encoded-project-path>/<session-uuid>.jsonl` — one file per session, appended as the session runs.

## Verified observables

| Observable | Where | Notes |
|---|---|---|
| Tool call | `assistant` record → `message.content[]` with `type: tool_use` | carries tool `name`, `id`, and `input` |
| Tool result | `user` record → `message.content[]` with `type: tool_result` | `is_error` is the green/red signal; `tool_use_id` pairs it to its call |
| Human turn | `user` record whose `message.content` is a string | distinguishes human input from tool results |
| Interruption | interrupt marker text inside a user message | counts as human braking |
| Model | `assistant.message.model` | synthetic entries prefixed `<` are excluded |
| Effort | `assistant.effort` | descriptive only, never scored |
| Token usage | `assistant.message.usage` | input, cache-read and cache-creation summed as input; output separate |
| Permission mode | `permission-mode` record → `permissionMode` | `bypassPermissions` = YOLO MODE, `plan` = plan entry |
| Compaction | any record with `isCompactSummary: true` | the verified marker |
| Timestamps | `timestamp` on most records | duration, night-shift hours, window bucketing |
| Test tallies | text of a tool result whose command looks like a test run | gated by command shape |

## Corrections worth remembering

**Compaction.** The first implementation looked for a `system` record with a `compact` subtype. No such record exists; a survey of 25 recent transcripts found zero matches, and a wider search found the real marker, `isCompactSummary: true` on a user record. The lesson generalises: verify a marker against real files before writing a detector, then pin it with a fixture test.

**Phantom test tallies.** The tally regex originally matched any tool output containing "N passed". During verification it read "86 passed" out of the grader's own rendered card, inside the session being graded, and recorded a fictional test regression worth −1,900 points. Tally parsing is now gated on the producing command matching a test-runner shape, and it fails open when nothing matches.

**Untrusted by construction.** Model and effort strings reach the card, so they are attacker-influenced text and are sanitised before rendering. See [design/card-spec.md](../design/card-spec.md).

## Not observable

Rate limits, billing, credit burn, UI freezes and provider-side incidents leave no trace in the transcript. Several genuinely common complaints therefore cannot become achievements, and were parked rather than faked. Task difficulty and code quality are likewise invisible — a passing command may be wrong work, which is why the score claims nothing about correctness.

## Format-coupling risk

This is an internal format with no stability guarantee; a Claude Code update can rename or restructure records. Containment: fixture-based tests that construct synthetic transcripts, tolerant parsing that skips malformed lines, and detectors that degrade to "did not fire" rather than crashing. A silent scoring change is the realistic failure mode, which is why every card stamps its scoring version and transcript hash.
