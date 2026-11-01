---
version: "1.0.0"
schema_version: 2
title: "Privacy Contract"
doc_type: detail
parent: docs/product/INDEX.md
last_updated: 2026-09-12
last_audit: 2026-08-19
audit_status: needs-review
domain: docs
triggers:
  - "llm grader privacy"
  - "zero upload"
  - "card allowlist"
---
# Privacy Contract

**Nothing leaves the machine, permanently, in this product family — and the rendered card carries only allowlisted fields.** This is a product promise, not a V1 limitation awaiting relaxation. Any future product that collects sessions must be a separately named product with its own install and its own consent, never a silent upgrade of this one.

## Why it is absolute

An AI-coding session transcript is among the most sensitive files on a developer's disk. It contains source code, file paths, internal hostnames, command output, customer data in fixtures, and credentials that leaked into logs. Most of it belongs to an employer or client who never consented to anything. Both external review waves independently concluded that the valuable form of this data is also the toxic form, and that deferring collection to "later" is how consent gets poisoned. Full findings: [research/review-ledgers.md](../research/review-ledgers.md).

## The three guarantees

1. **No network path.** The grading code performs no network I/O. A dependency or feature that introduces one into the grading path is a defect.
2. **Field allowlist on output.** A rendered card may contain: session-UUID prefix, date, duration, model and effort names, event counts, streak and window figures, token totals, modifier names and their reasons, the score components, the scoring version, and the recompute stamp. It may never contain prompt text, tool output, file paths, repository names, or branch names. See [design/card-spec.md](../design/card-spec.md) for the enforced list.
3. **Sharing is a human act.** The tool renders a card to a local file. Only the user moves it anywhere.

## How each guarantee is enforced

| Guarantee | Enforcement |
|---|---|
| No network path | Code review; no HTTP client is imported in the grading path |
| Field allowlist | `test_html_card_allowlist` plants secret prompt text, tool output, and paths in a fixture and asserts none reach the rendered card |
| Metadata safety | Model and effort strings come from the transcript and are sanitized to a conservative character set before rendering, so transcript-controlled text cannot inject markup or terminal escapes |
| Sharing is human | `--share` copies an allowlisted caption locally and opens a blank composer; the user pastes and posts. No automatic upload or posting exists |

## Known residual risks

- **The card is a disclosure surface by design.** A user who shares a card discloses their model, effort level, session shape, and token volume. That is acceptable because they chose to, and because no content is exposed.
- **A local history file would widen the retained-data surface.** Persistent badges are not built. If they are, the history schema needs its own allowlist — badge IDs, counters, schema version — and its own leak test, per the review finding on persisted state.
- **The recompute stamp is identity, not proof.** It detects edited numbers and modified scoring code; it does not certify that a transcript is genuine. See [design/scoring-model.md](../design/scoring-model.md) for the exact claim.
