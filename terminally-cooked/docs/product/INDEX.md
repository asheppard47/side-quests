---
version: "1.0.0"
schema_version: 2
title: "Product — Terminally Cooked"
doc_type: index
parent: INDEX.md
last_updated: 2026-08-20
last_audit: 2026-08-19
audit_status: current
domain: docs
triggers:
  - "llm grader product"
  - "llm grader concept"
  - "llm grader decisions"
---
# Product

**This section owns why Terminally Cooked exists, who it is for, what it promises, and which directions were deliberately closed.** Behavior specs live in [design/](../design/INDEX.md); implementation lives in [engineering/](../engineering/INDEX.md).

| Doc | Answers |
|---|---|
| [concept.md](./concept.md) | What is this, for whom, and why is it funny? |
| [privacy-contract.md](./privacy-contract.md) | What does the product permanently guarantee about user data? |
| [decision-log.md](./decision-log.md) | What was decided, when, and what was ruled out for good? |

## The one-paragraph pitch

Developers who run AI coding agents already stare at a hypnotic stream of red and green — failing and passing counts ticking up a diff at a time. Terminally Cooked turns one session of that into a scorecard: it reads the transcript already sitting on your disk, counts the greens, the errors, the streaks and the retries, and hands back named achievements — FLOW STATE for an unbroken run, DOOM LOOP for running the same failing command three times, YOLO MODE for the people who disable confirmation prompts. The number at the bottom means nothing, which is the joke; the recognition is the product.
