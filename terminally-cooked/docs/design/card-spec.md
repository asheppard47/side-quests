---
version: "1.0.0"
schema_version: 2
title: "Card Specification"
doc_type: detail
parent: INDEX.md
last_updated: 2026-08-21
last_audit: 2026-08-19
audit_status: current
domain: docs
triggers:
  - "llm grader card"
  - "card fields"
  - "html card"
  - "ansi card"
---
# Card Specification

**The card is the product's only artifact, and it may contain nothing beyond the allowlisted fields below.** Two renderers exist — an ANSI terminal card printed on every run, and a standalone HTML card written on `--html` — and both draw from the same field set so a shared card can never reveal more than a terminal one.

## Allowlisted fields

| Field | Source | Example |
|---|---|---|
| Session identifier | first 8 chars of the session UUID | `a3a4d4fb` |
| Date | first transcript timestamp, date only | `2026-08-19` |
| Duration | first-to-last timestamp | `5h 55m` |
| Models | model names, sanitized | `claude-sonnet-5` |
| Effort levels | effort values, sanitized | `high` |
| Event counts | successful tool results, tool errors, longest streak | `+36 tool results / 2 errors / streak 22` |
| Test tally pair | first and last test-shaped tallies | `86 tests passed → 129 tests passed` |
| Tool histogram | tool names and call counts, top 6 | `Bash:17 Read:4` |
| Token totals | summed usage | `483.3M in · 1.18M out` |
| Modifiers | name, class, value, reason line | `FLOW STATE ×1.5 — 64 green results without a miss` |
| Score | final, plus skill and comedy split | `+3,460 (skill 3,060 · comedy 400)` |
| Provenance | scoring version and recompute stamp | `scoring-v0.4 · recompute: transcript dc89… · code a4a8…` |

Forbidden without exception: prompt text, tool output, file paths, repository names, branch names, working directory, and any raw diff content. `test_html_card_allowlist` enforces this by planting each forbidden category in a fixture and asserting absence in the render.

## Untrusted fields

Model and effort names originate in the transcript and are therefore attacker-influenced. Both are stripped to `[A-Za-z0-9._+\- ]` and truncated before rendering, which neutralises HTML injection into the share card and terminal-escape injection into the ANSI card. `test_meta_injection_sanitized` covers it.

## Layout contract

The ANSI card is a live CLI readout and keeps log order (header → fever → counts → tally → modifiers → score at the bottom). The HTML/PNG share card is score-first so a Telegram or X crop hits the joke, not the meta line:

1. **Wordmark** — TERMINALLY COOKED
2. **Hero score** — display-size gold `+N`, then skill/comedy split and the entertainment line
3. **Stamp** — session id, date, duration, division; models and effort on the next line
4. **Counts then fever** — tool results, errors, streak, then the green-to-red bar (ratio of those tool results, not tests)
5. **Diff tally** — Claude Code +/- hunk stacked flush under the fever bar at the same width, red gutter touching the bar; first vs last test-run counts (`tests passed` / `failed`), `-` / `+` prefixes, no `#`
6. **Token totals**
7. **Modifier list** — glyph, name, value tag, reason (names wrap; they do not ellipsize)
8. **Footer** — scoring version and recompute stamp only

Same field allowlist, same GitHub-dark colors. A screenshot of either is still recognisably the same object; the share crop just leads with the number.

## Visual language

The card is a diff, not a dashboard. The ANSI terminal card stays GitHub-dark. The HTML/PNG share card is a yellow hazard sign for X: ground `#ffcc00`, type `#111` / `#333`, 3px `#111` edge, add `#0a7a2f`, remove `#b91c1c`. The gothic wordmark (`assets/logo.png`) bleeds to the card edges at the top. Score is 52px; nothing in the body type is smaller than 13px. Pad matches the yellow ground — that is the card, not a cream frame around a dark widget. Modifier class is encoded visually in both renderers: chains take gold, debuffs red, flavor inert. Glyphs are monochrome terminal-native codepoints, never emoji — a deliberate rejection of the gamification patterns this audience mocks.

## Badge art integration

Painted badge art is produced per modifier at three levels of detail (1024 px, 72 px, 32 px). The 72 px asset is the chip in the HTML card; the 32 px asset is a center-zoom crop with contrast and saturation boosts so the subject survives at tile size. The art itself is textless — names are drawn by the renderer, never painted into the image. Rationale and pipeline: [art/style-guide.md](../art/style-guide.md) and [art/production-pipeline.md](../art/production-pipeline.md).

## Output rules

The HTML card is a self-contained fragment with an explicit `<meta charset="utf-8">` — without it the glyphs render as mojibake, which shipped once and was caught by screenshot review. `--png` rasterizes that card with local Chrome, flood-fills edge-connected magenta (including Chrome's anti-aliased pink) so badge purples stay, and writes a cropped PNG with a short pad of the same card ground (no light frame). Rounded-corner leftovers inside the pad are filled with the card background. The files stay local; nothing transmits them. The skill opens the PNG when grading finishes.
