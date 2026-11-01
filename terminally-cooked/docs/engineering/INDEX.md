---
version: "1.0.0"
schema_version: 2
title: "Engineering"
doc_type: index
parent: INDEX.md
last_updated: 2026-09-12
last_audit: 2026-08-19
audit_status: needs-review
domain: docs
triggers:
  - "llm grader engineering"
  - "llm grader architecture"
  - "llm grader tests"
---
# Engineering

**This section owns how the tool is built, what it can observe, and how correctness is proven.** The behavior it implements is specified in [design/](../design/INDEX.md); the constraints it must never violate are in [product/privacy-contract.md](../product/privacy-contract.md).

| Doc | Answers |
|---|---|
| [architecture.md](./architecture.md) | What are the moving parts, auto-pick rules and limits, and data flow? |
| [transcript-observables.md](./transcript-observables.md) | What can Claude Code records expose, and how reliably? |
| [testing.md](./testing.md) | What is proven by synthetic fixtures, and how do I add to it? |

## Shape of the thing

Two Python modules handle grading and harness adapters, using the standard library. Local session records go in; an ANSI card and optional HTML or PNG card come out. PNG export uses local Chrome or Chromium. Badge assets ship with the code; grading has no upload or persistent score history.
