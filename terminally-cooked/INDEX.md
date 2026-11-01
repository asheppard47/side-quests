---
version: "1.0.0"
schema_version: 2
title: "Terminally Cooked — Doc Tree"
doc_type: index
parent: null
last_updated: 2026-11-01
last_audit: 2026-08-19
audit_status: needs-review
domain: docs
triggers:
  - "terminally cooked docs"
  - "llm grader docs"
  - "llm grader index"
  - "badge system docs"
---
# Terminally Cooked — Doc Tree

**Terminally Cooked grades one of your own AI-coding sessions into a comedy results card, entirely on your machine.** It reads a session transcript that already exists locally, counts what actually happened, attaches named achievement modifiers, and renders a card in the red/green diff-counter aesthetic. The score is entertainment and says so on the card. Nothing is uploaded, ever. Working title during build was LLM Grader.

This index is the entry point. Each section below owns one stage of the work and nothing else; every leaf answers its question in its first paragraph.

## Current state (2026-11-01)

| Dimension | State |
|---|---|
| Code | `grade_session.py` + `harness_adapters.py`, scoring v0.6, 100 test functions |
| License | MIT |
| Repo | `asheppard47/side-quests`, folder `terminally-cooked/` (renamed from `asheppard47/terminally-cooked` 2026-11-01; old URLs redirect) |
| Catalog | 24 modifiers across 3 classes — [design/modifier-catalog.md](./docs/design/modifier-catalog.md) |
| Badge art | Voted winners in `assets/badges/`, inlined as data URIs — [art/voting-protocol.md](./docs/art/voting-protocol.md) |
| Harnesses | Claude Code, Codex, Grok, Gemini CLI — card stamps the adapter |
| External review | 2 med-arb waves, a 3-seat adapter validation, and a 2-seat code review (2026-11-01) — [research/review-ledgers.md](./docs/research/review-ledgers.md) |
| Not built | Persistent badges/history, marketing lane |

## Sections

| Section | Owns | Start here |
|---|---|---|
| [docs/product/](./docs/product/INDEX.md) | Why this exists, what it promises, what was ruled out | [concept.md](./docs/product/concept.md) |
| [docs/design/](./docs/design/INDEX.md) | What the program does: scoring, catalog, card output | [scoring-model.md](./docs/design/scoring-model.md) |
| [docs/art/](./docs/art/INDEX.md) | How badges look and how they get made | [style-guide.md](./docs/art/style-guide.md) |
| [docs/engineering/](./docs/engineering/INDEX.md) | How it is built and verified | [architecture.md](./docs/engineering/architecture.md) |
| [docs/research/](./docs/research/INDEX.md) | Evidence behind the decisions | [review-ledgers.md](./docs/research/review-ledgers.md) |

## Binding constraints

Three rules outrank every other document here. Violating one is a defect, not a design choice.

1. **Zero upload, permanently.** No network code exists in this repo and none may be added to the grading path. → [product/privacy-contract.md](./docs/product/privacy-contract.md)
2. **Card fields are allowlisted.** No prompt text, file path, repo name, branch, or tool output may reach a rendered card. Enforced by test. → [design/card-spec.md](./docs/design/card-spec.md)
3. **The score is entertainment.** It is labeled as such on every surface, and no ranked leaderboard ships. → [product/decision-log.md](./docs/product/decision-log.md)

## Lineage

The concept came out of a 2026-08-18 workshop brainstorm that also produced an archived predecessor (a rhythm game on the same diff-counter aesthetic). This tree is the SSOT for how the product works. Audience-research headlines that shaped the catalog are in [docs/research/INDEX.md](./docs/research/INDEX.md). Private workshop notes are not in this repository and are not required to run the tool.
