---
version: "1.0.0"
schema_version: 2
title: "Concept and Audience"
doc_type: detail
parent: INDEX.md
last_updated: 2026-08-20
last_audit: 2026-08-19
audit_status: current
domain: docs
triggers:
  - "terminally cooked pitch"
  - "llm grader pitch"
  - "who is llm grader for"
  - "llm grader register"
---
# Concept and Audience

**Terminally Cooked is a self-deprecating scorecard for people who run AI coding agents: it grades a real session from the transcript on their own machine and returns comedy achievements instead of a performance review.** The product is recognition, not measurement — the value is a developer seeing "DOOM LOOP — same command failed 4x" and laughing because it happened an hour ago.

## Audience

Developers who use agentic coding CLIs — Claude Code, Codex CLI, Cursor, Gemini CLI. They are technical, allergic to corporate gamification, and fluent in a shared vernacular ("YOLO mode", "let it cook"). Evidence for that vernacular and for what this audience mocks is in the [X research capsule](../research/INDEX.md).

The CLI auto-detects Claude Code, Codex, Grok, and Gemini CLI session files. Cross-harness numbers are different games: every card stamps its adapter. See [decision-log.md](./decision-log.md) D17.

## Register

The tone is in-group roast: the tool is rude about *your* session in the way a friend who saw the whole thing would be. Three rules keep it there.

- **Punch at the session, never the person.** "Entered plan mode, edited nothing" is funny; anything implying the developer is bad at their job is not.
- **Never claim measurement.** The card says the score means nothing. Every surface repeats it. Precision plus authority is the failure mode — a specific number labeled "skill" reads as an assessment, so the card splits the total into a skill component and a comedy component and disclaims both.
- **No cutesy gamification.** Emoji badges, streak-as-status, and leaderboards are exactly the patterns this audience publicly mocks. Terminal-native glyphs and painted achievement art carry the humor instead.

## What "winning" looks like

The unit of success is a developer voluntarily screenshotting their card. That single behavior is the whole funnel: it validates the jokes, it markets the tool, and it is the only distribution mechanism the [privacy contract](./privacy-contract.md) permits, because the card is the only artifact that ever leaves the machine and the user is the one who moves it.

## Non-goals

- Not a productivity tool. It does not tell you how to code better, and any framing that implies it does is off-register.
- Not a benchmark. Sessions are not comparable across people, tasks, models, or effort levels, and the design deliberately refuses to pretend otherwise.
- Not a data product. That direction was investigated and killed on rights, leakage, and market grounds — see [decision-log.md](./decision-log.md).
