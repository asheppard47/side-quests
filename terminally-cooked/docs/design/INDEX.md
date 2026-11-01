---
version: "1.0.0"
schema_version: 2
title: "Design — Behavior Spec"
doc_type: index
parent: INDEX.md
last_updated: 2026-08-19
last_audit: 2026-08-19
audit_status: current
domain: docs
triggers:
  - "llm grader design"
  - "scoring spec"
  - "card spec"
---
# Design — Behavior Spec

**This section defines what the program does: how a session becomes a score, which achievements exist, and what the output card contains.** It is the contract the code in [engineering/](../engineering/INDEX.md) implements and the tests enforce.

| Doc | Answers |
|---|---|
| [scoring-model.md](./scoring-model.md) | How does a transcript become a number, and what does that number claim? |
| [modifier-catalog.md](./modifier-catalog.md) | Which achievements exist, what triggers each, and what is it worth? |
| [card-spec.md](./card-spec.md) | What does the output look like and which fields may appear? |
| [harness-adapters.md](./harness-adapters.md) | How would other agent CLIs (Codex, Grok, Gemini) be graded — detection, mapping, adapter design? |

## The design thesis in one line

Anyone can be lucky for ten minutes, so short bursts pay linearly and flat — but *sustained* error-free work is exponentially unlikely by luck, so it is the only thing that compounds.
