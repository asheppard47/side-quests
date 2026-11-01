---
name: terminally-cooked
description: >
  Grade a juicy AI-coding session from today into a local comedy results card
  (Terminally Cooked). Never grade the session that invoked this skill — that
  card has no insight. Use when the user says "grade this session", "grade my
  session", "session card", "terminally cooked", "llm grader", "roast this
  session", or wants a shareable diff-counter scorecard from a Claude Code,
  Codex, Grok, or Gemini CLI transcript.
---

# Terminally Cooked

Run the CLI in this repo. Do not reimplement scoring.

**Never grade the session you are currently in.** The invoking chat is a
probe, not a work session.

## Establish who invoked you

The CLI recognizes the invoking session by these environment variables:
`GROK_SESSION_ID`, `CODEX_THREAD_ID`, `CODEX_SESSION_ID`, `CLAUDE_SESSION_ID`,
`CLAUDE_CODE_SESSION_ID`. Before an auto-pick, check which one your harness
set. Claude Code sets `CLAUDE_CODE_SESSION_ID` (observed 2026-11-01); the CLI
recognizes no Gemini CLI variable, so a Gemini-invoked pick is always heuristic.

- **An id is set**: auto-pick excludes that session by id, and an explicit
  path or id prefix that matches it is refused with an error.
- **No id is set**: auto-pick still runs, but it excludes the newest session
  of every harness and the newest Claude transcript in this project as a
  heuristic. The pick note says so. Tell the user the exclusion was a guess,
  not identity, and name the session that was graded.

When the user says "this session", "grade this session" or "roast this
session", say which session you graded (its id prefix and length from the
card) and that it is not the chat you are in. Never grade another session
silently in its place.

```bash
python3 grade_session.py --png                  # auto-pick from today; cropped PNG + HTML
python3 grade_session.py --png <id-prefix>      # a specific other session
python3 grade_session.py --png path/to/session  # a file, or a Grok session dir
python3 grade_session.py --html                 # HTML only
python3 grade_session.py --share                # copy a caption locally; user pastes to X
python3 test_grade_session.py
```

Existing card files are never overwritten unless you pass `--force`. `--tz`
fixes the zone Night Shift reads hours in; the card stamps the zone used.

A Codex rollout file, a Grok session directory, or a Gemini chat file works
the same way when the user names a specific *other* session. The card stamps
the adapter. Cross-harness scores are different games.

Badge art lives in `assets/badges/` next to the script, and the wordmark is
`assets/logo.png`. Both are inlined as data URIs. Keep them with the script.
Never fetch art from the network.

## Repair without breaking intent

Transcript formats change. When a card looks wrong, an adapter fails open, or a
user reports a harness the parser does not understand, **fix detection and
parsing only**. The scoring contract is not yours to improve in passing.

**Allowed**
- Adapter / event-normalization fixes in `harness_adapters.py` so a real session
  shape maps onto the existing event contract. A repair must not change any
  score for a session shape that already parsed correctly; if it would, that is
  a scoring change and needs an owner decision and a new scoring-version string
- Fail-open on unknown records, unknown tool outcomes, and missing fields
- Tests that pin the new session shape (fixture + expected counts)
- Docs that describe the newly observed transcript field

**Forbidden without an explicit owner decision and a new scoring-version string**
- Changing weights, caps, exponents, or which modifiers multiply vs add
- Adding, renaming, or re-thresholding catalog entries to "make the joke better"
- Adding network calls, upload, telemetry, analytics, or remote badge URLs
- Putting prompt text, file paths, repo names, branches, or tool output on a card
- Removing or softening the entertainment label
- Imputing subagent / child-session work into the parent score
- Ranking, leaderboards, or any claim that scores are comparable across people
- Grading the invoking session "just this once"

If a format change makes a modifier unobservable, leave it unawarded. Do not
invent a proxy metric.

**Tool names.** Every `tool_call` event carries an allowlisted display `name`
(from `KNOWN_TOOLS`; MCP tools become `MCP`, anything else `Other`) and one
canonical `cls`: `shell`, `read`, `edit`, `agent`, `ask`, `plan`, or `other`.
Modifiers read the class, never a harness's raw tool name, and `command` is set
only for `shell`-class calls. A new built-in tool gets a `KNOWN_TOOLS` row with
its class; a raw name never reaches a card.

**Out of repair scope.** A privacy, card-field, or renderer defect you find
while repairing an adapter (a leak, an injection, a network request from the
PNG renderer) is reported to the owner for a decision. Do not patch it as part
of an adapter repair.

The allowlist, privacy contract, and scoring model are the intent. A green test
suite after an adapter fix is necessary and not sufficient: also confirm a real
file from that harness still grades, and that HTML contains no `http` badge
source.

## How to invoke

If the user names a known other session, run
`python3 grade_session.py --png <id-prefix or path>`. Otherwise run
`python3 grade_session.py --png` from this repo root, after checking the
invoker id as above. That writes a cropped PNG of the card (local Chrome with
its network services off, no upload) and opens it. Do not add a light or paper
frame around the image. Show the ANSI card too. Relay the pick note when it
says the exclusion was heuristic, or when the user asked about "this session";
otherwise mention it only if the user asks how the session was chosen. Do not
post the image; the user does.
