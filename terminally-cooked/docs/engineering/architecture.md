---
version: "1.0.0"
schema_version: 2
title: "Architecture"
doc_type: detail
parent: docs/engineering/INDEX.md
last_updated: 2026-09-12
last_audit: 2026-08-19
audit_status: needs-review
domain: docs
triggers:
  - "llm grader architecture"
  - "grade_session structure"
  - "data flow"
---
# Architecture

**A two-module pipeline — harness adapters normalize any supported CLI's session into one event stream; the grader consumes events through five separable stages: locate, analyze, judge, render, share.** Parsing knowledge lives entirely in `harness_adapters.py`; `grade_session.py` never touches a harness-specific field, which is what let three new harnesses land without changing a line of scoring.

## Data flow

```
find_session(arg)         → explicit path/prefix, or an auto-picked candidate
   ↓
detect_harness(path)      → claude-code | codex | grok | gemini   (content sniff)
   ↓
iter_events(path)         → normalized events (human / tool_call / tool_result /
   ↓                        model / usage / permission / compaction / interrupt)
analyze(path)             → stats dict: counts, streaks, windows, metadata, sha
   ↓
pick_buffs(stats)         → [(name, class, value, reason), …]
   ↓
score_parts(stats, buffs) → (core, flat)
   ↓
render / render_html      → ANSI card, HTML card (adapter stamped in provenance)
```

Tool-result success is **tri-state** (`True | False | None`): unknown outcomes (common in Codex rollouts, which carry no universal error boolean) count toward neither streaks nor spirals and surface on the card as `?N unknown`.

## Auto-pick selection and limits

No argument takes the auto-pick path; an explicit existing path or UUID prefix selects that requested session directly. Auto-pick gathers supported primary-session stores, excludes files over 50 MiB, and excludes Codex rollouts marked as subagents. It does **not** enumerate `~/.codex/archived_sessions/`.

It excludes every candidate matching a recognized `GROK_SESSION_ID`, `CODEX_THREAD_ID`, `CODEX_SESSION_ID`, `CLAUDE_SESSION_ID`, or `CLAUDE_CODE_SESSION_ID`. Independently, it also excludes the newest Claude JSONL in the project directory derived from the current working directory. Both checks run, so a foreign-harness ID does not suppress the Claude exclusion. Concurrent sessions in that same project can still make the newest Claude file the wrong exclusion. If neither check produces a match, it excludes the globally newest candidate by mtime. Neither recency fallback proves invoker identity; the product rule remains never grade the invoking session.

After exclusions, the scoring pool is the union of every under-cap candidate modified since local midnight and the 20 most recently modified under-cap candidates from the seven-day lookback, deduplicated by resolved path. Those 20 include today's candidates; if today supplies at least 20 candidates, no older candidate enters the pool. If none falls within the lookback by modification time, the 20 are taken from all remaining candidates. Therefore the current path has no fixed cap for today and does not inspect every older session in the week. Unreadable candidates are skipped.

Final selection uses a candidate's first normalized event timestamp, falling back to file mtime when that timestamp is missing or invalid. Only ages from zero through seven calendar days qualify, so an older fallback candidate can be parsed without becoming eligible, and selection may still find nothing. Selection order is sessions lasting at least five minutes from today, then from the lookback, then shorter probes from today, then probes from the lookback. The highest positive juice score within the first nonempty group wins. Juice counts known and unknown tool results and weights duration; it measures selection activity, not the entertainment score.

## Responsibilities

| Function | Owns | Never does |
|---|---|---|
| `find_session` | resolving a path or UUID prefix, or delegating to auto-pick | rendering a card |
| `pick_juicy_session` | excluding recognized invoker IDs and the newest Claude transcript in the current project, then selecting from the current candidate set | proving identity when neither signal is available |
| `iter_records` | streaming JSONL, skipping malformed lines | interpreting semantics |
| `analyze` | one pass producing every observable — counts, streaks, doom-loop runs, cook chain, time windows, tokens, models, effort, compaction, transcript hash | any scoring judgment |
| `pick_buffs` | the catalog: thresholds, classes, reason strings | arithmetic on the total |
| `score_parts` | the formula, caps, exponents, floor | deciding which modifiers fired |
| `render`, `render_html` | presentation, glyphs, layout | recomputing anything |
| `safe_meta` | sanitising transcript-sourced metadata for output | filtering content elsewhere |
| `fingerprint` | recompute identity stamp | claiming authenticity |

The single `analyze` pass is deliberate: streaks, spirals, doom-loop runs and window occupancy are all sequence-dependent, and computing them in separate passes invites disagreement between them.

## Key mechanics

**Streak and spiral** track consecutive non-error and error tool results respectively, each resetting the other.

**Doom loop** pairs a `tool_use` id to its command text in a pending map, then on the matching `tool_result` compares the command to the last failed command; identical and failed increments the run, any success clears it. Command text is used for comparison only and never rendered.

**Cook chain** counts consecutive green tool results with no intervening human text; a human message or an error resets it, so it measures unsupervised *success*, not unsupervised volume.

**Clean-window chain** buckets tool results into fixed 20-minute windows keyed off the first timestamp, marks a window clean when it holds at least 5 events and no errors, and walks the buckets: clean extends the run, an error resets it, one sparse window holds it, two consecutive sparse windows reset it. Negative bucket indices from out-of-order timestamps are discarded rather than silently folded into bucket zero.

## Interfaces

```bash
python3 grade_session.py                  # auto-picked candidate
python3 grade_session.py a3a4d4fb         # by UUID prefix
python3 grade_session.py path/to/x.jsonl  # explicit path
python3 grade_session.py --html [out.html]
```

Exit is non-zero with a clear message when no transcript matches. `FORCE_COLOR=1` forces ANSI color when stdout is not a TTY.

## Dependencies

Grading uses the standard library only. Pillow is required for the badge art pipeline and for the injection test's fixtures, not for grading. The supported transcript formats are internal and version-dependent; [harness-adapters.md](../design/harness-adapters.md) owns their locations, format-specific limits, and containment.
