---
version: "1.0.0"
schema_version: 2
title: "Architecture"
doc_type: detail
parent: docs/engineering/INDEX.md
last_updated: 2026-11-01
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

No argument takes the auto-pick path; an explicit existing path or id prefix selects that requested session directly, unless its id matches the invoker (below), in which case the CLI refuses with an error. Auto-pick gathers supported primary-session stores and excludes Codex rollouts marked as subagents. It does **not** enumerate `~/.codex/archived_sessions/`.

Live-session exclusion runs over that **unfiltered** list, before any size cap. When `GROK_SESSION_ID`, `CODEX_THREAD_ID`, `CODEX_SESSION_ID`, `CLAUDE_SESSION_ID`, or `CLAUDE_CODE_SESSION_ID` matches a candidate's id, that is identity and only the matching session is excluded. The match uses the id in the given name, the resolved target's name and the transcript's own session id, so an explicit symlink alias or renamed copy of the live session is refused too. When no recognized id matches, exclusion is a disclosed heuristic: the newest session of every harness store and the newest Claude transcript in the current working directory's project folder are all excluded, and the pick note says the exclusion was heuristic. A live session that is not the newest of its harness (an older session still being written while a newer one exists) can still be missed without an id; that is the residual limit.

After exclusions, files over 50 MiB are dropped. The shortlist is today's candidates (newest first) followed by the seven-day lookback (newest first), deduplicated by resolved path and capped at 20 in total, so today's files count toward the cap. If none falls within the lookback by modification time, the lookback is taken from all remaining candidates. Unreadable candidates are skipped.

Final selection uses a candidate's first normalized event timestamp, falling back to file mtime when that timestamp is missing or invalid. Only ages from zero through seven calendar days qualify, so an older fallback candidate can be parsed without becoming eligible, and selection may still find nothing. Selection order is sessions lasting at least five minutes from today, then from the lookback, then shorter probes from today, then probes from the lookback. The highest positive juice score within the first nonempty group wins. Juice counts known and unknown tool results and weights duration; it measures selection activity, not the entertainment score.

## Responsibilities

| Function | Owns | Never does |
|---|---|---|
| `find_session` | resolving a path or UUID prefix, or delegating to auto-pick | rendering a card |
| `pick_juicy_session` | excluding the invoker by id, or heuristically (newest per harness and in this project) with a note saying so, then selecting from a capped shortlist | proving identity when no id is available |
| `write_output` | refusing source-file, existing-file and symlink destinations without `--force`; publishing by exclusive hard-link create (fail closed where unsupported), or `os.replace` under `--force` | following a symlink destination; check-then-replace |
| `harness_adapters._iter_jsonl` | streaming JSONL, skipping malformed lines and non-object records | interpreting semantics |
| `analyze` | one pass producing every observable — counts, streaks, doom-loop runs, cook chain, time windows, tokens, models, effort, compaction, transcript hash | any scoring judgment |
| `pick_buffs` | the catalog: thresholds, classes, reason strings | arithmetic on the total |
| `score_parts` | the formula, caps, exponents, floor | deciding which modifiers fired |
| `render`, `render_html` | presentation, glyphs, layout | recomputing anything |
| `card_fields`, `safe_meta`, `clean` | the only dynamic values a card, caption or filename may print, re-validated (id-shaped ids, `YYYY-MM-DD` dates, sanitized names, control characters stripped) | filtering content elsewhere |
| `fingerprint` | recompute identity stamp: session-file hash, both modules' code hash, time zone | claiming authenticity |

The single `analyze` pass is deliberate: streaks, spirals, doom-loop runs and window occupancy are all sequence-dependent, and computing them in separate passes invites disagreement between them.

## Key mechanics

**Streak and spiral** track consecutive non-error and error tool results respectively, each resetting the other.

**Doom loop** pairs a shell-class `tool_call` id to its command text in a pending map, then on the matching `tool_result` compares the command to the last failed command; identical and failed increments the run, a successful shell command clears it, and non-shell tools in between leave it alone (per the catalog). Command text is used for comparison only and never rendered.

**Cook chain** counts consecutive green tool results with no intervening human text; a human message or an error resets it, so it measures unsupervised *success*, not unsupervised volume.

**Clean-window chain** buckets known-outcome tool results into fixed 20-minute windows keyed off the first timestamp, marks a window clean when it holds at least 5 events and no errors, and walks every bucket before the one holding the session's latest timestamp (any event, not only tool results): clean extends the run, an error resets it, one sparse window holds it, two consecutive sparse windows reset it. Negative bucket indices from out-of-order timestamps are discarded rather than silently folded into bucket zero. Timestamps are parsed by `parse_ts`, which normalizes `Z`, compact offsets and any fraction length so Python 3.9 reads them.

## Interfaces

```bash
python3 grade_session.py                  # auto-picked candidate
python3 grade_session.py a3a4d4fb         # by UUID prefix
python3 grade_session.py path/to/x.jsonl  # explicit path
python3 grade_session.py a3a4d4fb --html [out.html] [--force]
python3 grade_session.py a3a4d4fb --png [out.png] --tz UTC-07:00
```

Put the session first: `--html` and `--png` take an optional destination and refuse one without a `.html`/`.png` extension, so `--png a3a4d4fb` is an error, not an auto-pick that writes over a file named after the session.

Exit is non-zero with a clear message when no transcript matches. `FORCE_COLOR=1` forces ANSI color when stdout is not a TTY.

## Dependencies

Grading uses the standard library only. Pillow is required for the badge art pipeline and for the injection test's fixtures, not for grading. The supported transcript formats are internal and version-dependent; [harness-adapters.md](../design/harness-adapters.md) owns their locations, format-specific limits, and containment.
