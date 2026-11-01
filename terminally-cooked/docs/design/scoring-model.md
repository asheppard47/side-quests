---
version: "1.0.0"
schema_version: 2
title: "Scoring Model (v0.4)"
doc_type: detail
parent: INDEX.md
last_updated: 2026-08-19
last_audit: 2026-08-19
audit_status: current
domain: docs
triggers:
  - "llm grader scoring"
  - "scoring formula"
  - "chain multiplier"
  - "clean window chain"
---
# Scoring Model (v0.4)

**Serialized success is the only thing that multiplies, sustained success is the only thing that compounds superlinearly, and everything else adds a flat comedy bonus that can never inflate the rest.** The resulting number is entertainment; it is labeled as such and split on the card into a skill component and a comedy component so the disclaimer is structural rather than a footnote.

## The formula

```
core  = green×10 − red×15
      + min(streak, 100) ^ 1.5                       # serialized events
      + 150 × min(clean_windows, 12) ^ 1.5           # sustained performance
      + (last_pass_count − first_pass_count) × 25    # verified test movement

FINAL = max(0, core × chain × debuff) + flat
```

- `chain` — product of all chain-class modifiers, capped at **6.0**
- `debuff` — product of all debuff-class modifiers, uncapped downward
- `flat` — sum of all flavor-class modifiers, added after the floor

## Why each term is shaped that way

**Exponent 1.5 on streaks and windows.** A linear reward treats a 100-long streak as ten times a 10-long streak, which understates it: each additional error-free step is conditionally less likely than the last. The 1.5 exponent pays a 100-streak roughly 32× a 10-streak. Caps at 100 events and 12 windows keep an outlier session from running away.

**The clean-window chain is the centrepiece.** A long streak can be ten lucky minutes of cheap calls. Consecutive 20-minute windows, each holding at least 5 tool events with zero errors, cannot be luck at length — sustaining it for two hours is the genuinely rare thing. One quiet window holds the chain (thinking is allowed); two consecutive quiet windows reset it (walking away is not a chain).

**Chains multiply, flavor adds.** Multiplying circumstance (a long session, a big token bill, three models) inflates the score for things that took no skill and stack trivially. Under v0.4 those became flat points, and the multiplier lane is reserved for evidence of serialized decisions.

**Cap and floor.** The 6.0 chain cap is the "within reason" bound on stacking. The floor keeps a disastrous session at zero rather than negative, and flavor lands after the floor deliberately: comedy survives failure, so a catastrophic session still earns YOLO MODE points and still prints a funny card.

**Correlated chains collapse.** ONE-SHOT WONDER, FLOW STATE and Clean Streak all describe the same underlying streak, so they form one exclusive group — only the strongest applies. Without that, one good run would multiply itself three times.

## Worked examples

Both are real sessions, same scoring version.

**A 6-hour session, 36 green, 2 errors, 22-streak, no window chain**

```
core = 36×10 − 2×15 + 22^1.5           = 360 − 30 + 103   = 433
chain = 1.2 (Clean Streak)   debuff = 0.9 (Twenty Questions)
FINAL = 433 × 1.2 × 0.9 + 400 (Night Shift, Marathon)      ≈ 868
```

**A 36-hour session, 439 green, 19 errors, 81-streak, 6 clean windows, tests 86 → 129**

```
core  = 439×10 − 19×15 + 81^1.5 + 150×6^1.5 + 43×25
      = 4,390 − 285 + 729 + 2,204 + 1,075                  = 8,113
chain = 1.5 (FLOW STATE) × 1.6 (THE LONG GAME)             = 2.4
debuff = 0.9 (Twenty Questions) × 0.8 (Backseat Driver)    = 0.72
FINAL = 8,113 × 2.4 × 0.72 + 800 flavor                    ≈ 14,819
```

The composition matters more than the total: in the second example the two sustained-performance terms contribute nearly 3,000 points before any multiplier, which is the design working as intended.

## What the number does not claim

A tool result that did not error counts as green. That is *execution* success, not task success — a passing command can still be wrong work. Test tallies are only read from commands that look like test runs, which stops a card or a log quoting "86 passed" from poisoning the delta, but the parse remains a heuristic that fails open. Conditions such as model and effort are displayed and never scored. The score is therefore a joke with arithmetic behind it, not a measurement.

## Canonical unit and comparability (v0.5)

**The canonical scoring unit is one complete native session transcript, graded from its first record to grading time — never a rolling lookback, never a best-session ladder.** A rolling window invites slicing errors out of the boundary; a best-possible ladder rewards grinding and cherry-picking. The session boundary is the one boundary the source system supplies for free, so it is the only honest unit.

Comparability is carried by an identity tuple, not the number alone. A shared card states: scoring version, session **division** (blitz &lt;15 min, sprint &lt;2 h, long haul beyond — labels like chess time controls, never normalizers), **delegation class** (a session with subagent calls prints "internals not graded"), duration, and the recompute stamp. Equal totals from different divisions or delegation classes are different games, and the card says so.

Two rules inside the unit keep it honest: only **completed** 20-minute windows qualify for the sustained-skill chain (the in-progress final bucket never counts, so three windows cannot be earned in twenty-one minutes), and test-tally deltas compare only runs of the **same test command**, so a full suite followed by one focused test cannot register as a fictional regression.

## Versioning and recomputation

Every card stamps its scoring version and a recompute identifier: the transcript's SHA-256 prefix plus a hash of the scoring code. Rerunning the official script on the same transcript must reproduce the score, which detects edited numbers and modified scoring code. It does **not** prove a transcript is genuine — a hand-authored transcript hashes just fine. Deterrence against that is economic: the score is explicitly worthless, and no ranking rewards forging it.
