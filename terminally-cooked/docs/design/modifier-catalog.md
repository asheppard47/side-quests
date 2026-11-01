---
version: "1.0.0"
schema_version: 2
title: "Modifier Catalog"
doc_type: detail
parent: INDEX.md
last_updated: 2026-08-19
last_audit: 2026-08-19
audit_status: current
domain: docs
triggers:
  - "llm grader badges"
  - "achievement list"
  - "modifier catalog"
  - "buff list"
---
# Modifier Catalog

**Twenty-four modifiers in three classes: chains multiply the core score, debuffs divide it, and flavor adds flat comedy points.** A modifier's class is a design statement — multiplying is reserved for evidence of serialized success, per [scoring-model.md](./scoring-model.md). Every entry must be computable from a local transcript alone; a joke with no observable does not ship.

## Chains — multiply, capped at 6.0 product

The streak group (first three rows) is mutually exclusive: only the strongest applies, because all three describe the same run.

| Modifier | Trigger | Value | Glyph |
|---|---|---|---|
| ONE-SHOT WONDER | zero errors across ≥20 tool results | ×1.6 | ◎ |
| FLOW STATE | longest streak ≥25 | ×1.5 | ≋ |
| Clean Streak | longest streak 10–24 | ×1.2 | ⇉ |
| LET IT COOK | ≥50 consecutive green tool calls with no human input; any error resets | ×1.3 | ♨ |
| THE LONG GAME | ≥3 consecutive clean 20-minute windows | ×(1.0 + 0.1 per window, ≤12) | ♟ |

## Debuffs — multiply down

| Modifier | Trigger | Value | Glyph |
|---|---|---|---|
| Red Wedding | test failure count increased | ×0.6 | ☠ |
| Error Spiral | ≥4 consecutive errors | ×0.7 | ↺ |
| Doom Loop | identical Bash command failed ≥3 times; a successful rerun of a Bash command resets the run (intervening Reads do not — retrying after looking around is the joke) | ×0.7 | ↻ |
| Backseat Driver | ≥3 human interruptions | ×0.8 | ‼ |
| All Plan No Game | entered plan mode, zero Edit/Write tool calls (edits made via Bash or MCP tools are invisible to this trigger — known coarseness) | ×0.8 | ☰ |
| Twenty Questions | agent asked the human ≥4 questions | ×0.9 | ¿ |
| Third Time's the Charm | exactly 3 consecutive errors followed by a successful result (the recovery is required) | ×0.9 | ☘ |
| Overloaded | tool error matching overloaded / 529 | ×0.9 | ⏻ |

## Flavor — flat points, never compound

| Modifier | Trigger | Points | Glyph |
|---|---|---|---|
| YOLO MODE | session ran in bypass-permissions mode | +250 | » |
| Token Bonfire | ≥100M input tokens or ≥1M output tokens | +200 | 🜂 |
| Night Shift | ≥10 events between 02:00 and 06:00 local | +200 | ☾ |
| Marathon | session ≥4 hours | +200 | ∞ |
| Test Whisperer | pass count rose, from test-shaped commands only | +150 | ✓ |
| Speedrun | ≤10 minutes with ≥10 results | +150 | ↯ |
| Middle Manager | ≥5 subagent delegations | +150 | ⑂ |
| Lost the Tapes | survived ≥1 context compaction | +100 | ⌫ |
| Model Hopper | ≥3 distinct models in one session | +100 | ⇄ |
| Bookworm | ≥20 file reads and more reads than shell commands | +50 | ¶ |
| Perfectly Balanced | nothing else triggered | +0 | ≍ |

## Provenance

Five entries came from the 2026-08-18 X research sweep rather than invention: **YOLO MODE** and **LET IT COOK** are the audience's own vocabulary (8+ and 4+ distinct authors respectively), **Token Bonfire** reflects the one artifact developers demonstrably screenshot (token and cost dashboards), and **Overloaded** and **All Plan No Game** came from observable complaint shapes. An invented entry named "YOLO Ops" was deleted when the real meme's real observable was found. Details: [research/INDEX.md](../research/INDEX.md).

## Adding a modifier

1. Name the observable first. If the transcript cannot detect it deterministically, it is not a candidate — park it with the missing observable named.
2. Choose the class by the doctrine, not by how much you like the joke: does it require *serialized* success (chain), is it a failure (debuff), or is it circumstance (flavor)?
3. Write the trigger as a threshold with a reset rule where a sequence is involved.
4. Add a regression test covering the trigger and at least one near-miss.
5. Add a glyph for the terminal card and a prompt for the badge art, following [art/style-guide.md](../art/style-guide.md).

## Parked candidates

Observables exist or are partially verified, but no entry ships yet: overnight-run-that-worked (timestamps spanning sleep hours ending green) and per-tool failure taxonomies. Cross-session and lifetime achievements are deliberately excluded — see [product/decision-log.md](../product/decision-log.md).
