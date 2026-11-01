---
version: "1.0.0"
schema_version: 2
title: "External Review Ledgers"
doc_type: detail
parent: INDEX.md
last_updated: 2026-11-01
last_audit: 2026-08-19
audit_status: current
domain: docs
triggers:
  - "med arb findings"
  - "review ledger"
  - "external critique"
---
# External Review Ledgers

**Three external review passes shaped this product: two adversarial design reviews that killed the original business model and rebuilt the scoring system, and one game-industry icon review that rewrote the art pipeline.** Each is recorded with what was confirmed, what was rejected, and why — a rejected finding is as load-bearing as an accepted one.

## Wave 1 — concept review (2026-08-18)

Two external reviewers, one wave, on the full concept brief. One returned 24 findings including 8 critical; the other returned 40 findings including 8 critical. They converged independently, which is itself signal. Ten clusters after deduplication:

| Cluster | Ruling |
|---|---|
| Contributors cannot license employer work product | CONFIRMED — kills dataset sales |
| "Synthetic" derivation cures neither rights nor leakage | CONFIRMED — kills dataset sales |
| No buyer; labs hold better first-party traces with legal cover | CONFIRMED — kills dataset sales |
| A post-hoc tool cannot reconstruct the event ledger | **REJECTED** — Claude Code persists a full ordered local transcript; the reviewers lacked that context |
| Priority contradiction: corpus called the goal, V1 collects nothing | CONFIRMED — split into two products, kept the fun one |
| A comedy funnel selects the wrong population for research data | CONFIRMED — reinforced the marketing-only reshape |
| Deferred collection is a purpose change that poisons consent | CONFIRMED — zero-upload made permanent |
| Condition multipliers are theatre; an honor-system board is meaningless | CONFIRMED — hosted board killed, conditions demoted to descriptive |
| Session unit undefined; "diff economy" is not an observable | CONFIRMED — unit frozen, metric dropped |
| Fever-meter plus engine scope recreates the killed predecessor | CONFIRMED — CLI and local HTML only |

## Wave 2 — scoring review (2026-08-19)

One reviewer at high effort returned 11 findings on the v0.4 scoring redesign. The second leg failed twice on execution-budget kills and was reported unavailable rather than substituted.

| Finding | Ruling and action |
|---|---|
| Chain class does not reliably mean serialized decisions | PARTIAL — LET IT COOK made error-aware; Test Whisperer demoted to flavor; ONE-SHOT WONDER kept as a genuine zero-error sequence |
| Correlated chains double-count toward the cap | CONFIRMED — streak-derived chains collapsed into one exclusive group |
| Sparse windows hold the chain indefinitely | CONFIRMED, real bug — one quiet window holds, two reset |
| Out-of-order timestamps corrupt window bucketing | CONFIRMED — negative bucket indices discarded |
| Fingerprint overclaims verification | CONFIRMED — relabeled a recompute identifier, with the narrower claim documented |
| Transcript-controlled metadata can inject markup or escapes | CONFIRMED, best catch of the wave — sanitisation added with a test |
| Test tallies are naive and farmable | PARTIAL — impact defused by demotion to flavor; parsing later gated on test-shaped commands after a live failure |
| Doom loop is not strictly adjacent | PARTIAL — the joke tolerates intervening reads; card copy corrected to drop the "in a row" claim |
| Fixed wall-clock windows measure session shape | ACCEPTED AS COARSE — rolling windows rejected for complexity, limitation documented |
| Tool success is not task success | ACCEPTED AS COARSE — the card says "green results", never "wins" |
| Flavor survives a failed session | INTENTIONAL — comedy survives failure; card now splits skill and comedy so the total is not misread |

## Wave 3 — icon review (2026-08-19)

A vision model briefed as a game-industry icon designer reviewed the rendered set at true display sizes on the real card background.

| Severity | Finding | Action |
|---|---|---|
| Blocker | Baked-in nameplates consume ~15% of canvas and become sub-pixel noise at 32 px | Names moved to the UI layer; art regenerated textless |
| Major | High-frequency detail collapses into mush at small sizes | "Bold primary shapes, no micro-debris" added to the template |
| Major | Monochrome warm palettes lose their silhouette on a dark UI | Rim-light halo and value separation made mandatory |
| Major | Inconsistent framing and palette across the set | Locked palette, locked framing, and per-badge focus modes |
| Fix | Naive downscaling wastes the tile | Dedicated 32 px level of detail with center-zoom crop and boosted contrast |

## Wave 4 — publish-readiness review (2026-08-20)

Three seats fired on the full bundle (code + design docs) against seven publish questions; two returned (one at high effort with 16 findings, one with 9 findings), and the third — grok — was killed at its execution budget twice and reported unavailable. That is now four consecutive budget kills for that seat on code-review bundles: treat it as unsuitable for that packet shape rather than retrying a fifth time.

Confirmed and fixed in scoring v0.5: per-command test tallies (a full suite followed by one focused test read as −499 tests — both reviewers, critical), Third Time's the Charm now requires the recovery its spec always claimed, only completed 20-minute windows qualify for the sustained chain, broader test-runner detection, full HTML escaping of every interpolation, honest All Plan No Game wording, delegation class and session division on the card, `--share` caption-to-clipboard flow, and `--projects-dir` / `$CLAUDE_CONFIG_DIR` packaging support.

Adjudicated conflicts: subagent handling (classification over imputed weights — never fabricate precision about invisible work), share-to-X (blank composer + clipboard over prefilled intent URLs, which transmit the score before posting), scoring standard (complete-session unit with divisions-as-labels; a second "normalized" score was rejected as a reborn comparability claim), and an HMAC verification slug rejected as forgeable theater under a public salt. Verdicts recorded as D12–D16 in the decision log.

## Wave 5 — adapter-implementation validation (2026-08-20)

Each vendor's model validated its own harness's adapter. Gemini Flash: SHIP WITH FIXES — and caught a genuine critical in its own harness that the real-file smoke had missed: Gemini tool calls progress `running → completed` across repeated records, and the adapter locked the outcome at the first status seen, turning every completed call into an unknown (fixed: results emit only on terminal statuses). Sol: DO NOT SHIP, verified against local rollouts — token accounting both double-counted cache (`input_tokens` already includes cached; `total == input + output`) and re-counted cumulative snapshots (fixed: final totals only); current rollouts carry user turns as role-user `response_item.message`, not `event_msg.user_message` (fixed: both accepted); `function_call` commands live in JSON `arguments`, not `input` (fixed: parsed); and unknown-outcome results could still earn "clean" windows (fixed: unknowns populate no window). Also adopted: plan-mode from `collaboration_mode.kind`, bounded content sniffing with BOM tolerance and home-directory fallbacks, chunked hashing, null-safe token fields, fallback ids for anonymous Gemini calls. Grok's seat was budget-killed a fifth consecutive time — this time on a 13KB single-file packet — and is now considered unavailable for code-validation packets generally, not just large bundles; its harness's adapter ships validated by tests and real-file smoke only, flagged as such.

The wave's meta-lesson: real-file smoke tests validate the happy path of the files you happen to have. Two of the three critical defects (Gemini status progression, Codex role-user turns) existed only in session shapes absent from this machine's samples — vendor-model review caught what local data could not.

## Wave 6 — code review (2026-11-01)

Two independent reviewers, GPT-6 Astra and Gemini 4 Argon, read the full code, tests, skill and docs. Astra returned 13 findings (1 blocker, 9 major, 3 minor); Argon returned 10 (3 blockers, 5 major, 2 minor). They converged on the privacy boundary, invoker exclusion, tally parsing and the PNG renderer. The owner approved fixing every blocker and major in one change, recorded as D21 (scoring v0.6).

| Cluster | Ruling |
|---|---|
| Filename-derived ids and raw tool names reach cards, captions and filenames; ANSI escapes print unfiltered | CONFIRMED, blocker (both) — ids only from id-shaped names, else the transcript hash; allowlisted tool labels with a generic `MCP`; control characters stripped from every render path; adversarial CLI test |
| Auto-pick can grade the live session: stale same-cwd Claude files short-circuit exclusion, the size cap runs first, explicit targets skip the invoker check | CONFIRMED, blocker (both) — exclusion over the unfiltered list, id match is identity, no-id fallback excludes newest per harness and in-project and says so, matching targets refused |
| PNG renderer launches Chrome without network isolation | CONFIRMED, blocker (Argon; Astra major) — network-off flags and a CSP; claim narrowed to those controls. Astra's request for a network-observation test is not met: no stdlib way to observe Chrome's traffic, recorded as a residual risk |
| Failures-first and semicolon tallies read as zero failures; ties broken by insertion order | CONFIRMED (both) — counts parsed independently per summary line; cargo lines summed; ties go to the larger suite |
| `cat test_x.txt` and `echo '… passed'` qualify as test commands; `apply_patch` bodies treated as commands | CONFIRMED (both) — runner-invocation recognition by shell token; commands only for shell-class tools |
| Codex outcome trusts status-like text in stdout | CONFIRMED (Astra) — envelope header only (`Exit code:`, `Process exited with code`, JSON metadata); formats rechecked against local rollouts |
| Gemini usage doubled; Claude compaction and reminder records counted as human; Codex turns double-counted; non-object records crash adapters and discovery | CONFIRMED (both) — per-message snapshots, record-level human detection, one Codex stream with context items skipped, type guards throughout |
| Modifiers hard-code Claude tool names; Codex plan + `apply_patch` earns All Plan No Game; Grok results have no text | CONFIRMED (Argon) — canonical tool classes from the adapters; Grok output read from `updates.jsonl` |
| Completed windows judged by the last tool result | CONFIRMED (both) — bucket of the latest session timestamp |
| Doom loop survives intervening successful edits | REJECTED (Argon) — the catalog defines the reset as a successful shell command and says intervening reads do not reset; that is the joke, kept unchanged |
| Recompute stamp misses the adapters, Grok checkpoints and the time zone | CONFIRMED (both) — code hash over both modules, checkpoint entries hashed, zone explicit (`--tz`) and stamped |
| Output can overwrite the source transcript; existing files and symlinks are clobbered | CONFIRMED (Astra) — source and existing destinations refused without `--force`, symlinks never followed, atomic writes |
| Chrome killed 400 ms after the file appears; truncated PNG tracebacks | CONFIRMED (Argon) — wait for exit or a complete PNG; codec errors become a clean CLI error |
| Today's files bypass the analysis cap | CONFIRMED (Astra) — cap applies to the final shortlist |
| Python 3.9 rejects fraction lengths other than 3 or 6 | CONFIRMED (Argon) — timestamps normalized before parsing; suite run on 3.9.6 |
| HTML card omits unknowns and the tool histogram the spec lists | CONFIRMED (Argon) — HTML now shows both |
| Skill and README overstate exclusion, resilience and network claims | CONFIRMED (both) — invoker procedure, "this session" disclosure, tool classes, repair scope and claims rewritten |
| `--share` does nothing on Linux | DECLINED — out of scope for this wave |

**Pre-push verification (Sol).** A cross-family review of the v0.6 change (GPT-6.1 Sol, static read) returned HOLD with one blocker and seven majors. The owner accepted all eight; each fix carries a regression test that failed first, and all ship inside scoring-v0.6.

| Finding | Ruling |
|---|---|
| Symlink alias or renamed copy bypasses recognized invoker exclusion | CONFIRMED, blocker — identity from the given name, the resolved target and the transcript's own session id (Claude `sessionId`, Codex `session_meta`, Gemini header, Grok `info.id`); display label kept separate |
| Model and effort text such as `acme-private-repo` reaches every card | CONFIRMED — vendor id shapes only (`claude-`, `gpt-`, `o<digit>`, `codex-`, `gemini-`, `grok-`, length-capped), else `other model`; effort from six known levels, else `other`; no fixed model list, so new models keep working |
| Documented `--png <session>` consumes the session as the destination | CONFIRMED — every example puts the session first; `--png`/`--html` refuse a destination without the card extension |
| Quoted separators and compound commands manufacture tallies | CONFIRMED — a tally counts only from a lone runner after `cd <dir> &&` / `VAR=value` prefixes; pipes, later chains, substitution, subshells and stdout redirection are unscored; operators found in the raw string with quoting respected |
| Valid JSON with list-typed `type` or ids crashes the CLI | CONFIRMED — discriminators and correlation ids validated as strings at the adapter boundary |
| Final timestamps lost to Gemini dedup and Codex final messages | CONFIRMED — a timing-only tick per timestamped record; ticks never touch counts, streaks or Night Shift |
| XML-prefixed Codex prompts discarded as context | CONFIRMED — exact injected markers only (from local rollouts); `<task>…</task>` is a human turn |
| No-overwrite fallback can replace a file created in the race window | CONFIRMED — without `--force`, publish only by exclusive hard-link create and fail closed otherwise |
| Owner amendment to the compound-command ruling | A trailing pipeline of output filters after the runner counts (`pytest -q 2>&1 \| tail -20`); any other pipeline command still leaves the tally unscored |
| Repair check (Sol): a transcript renamed without `.jsonl` bypasses invoker exclusion | CONFIRMED, blocker — identity sniffs content under any extension; the grader parses the target by content and re-checks identity on the exact path |
| Repair check (Sol): filter options replace or inject output (`cat -<file`, `grep -H --label`, `sort --files0-from`) | CONFIRMED — explicit option and operand allowlist per filter; any `<` input redirection is unscored |

## Practices worth keeping

- **Review the plan before spending.** The X research plan was reviewed before any metered call; the reviewers rewrote the queries, added anti-promotion filters, and forced observability tagging at collection time. That pass prevented an entire wasted research budget.
- **Report failed legs honestly.** Two reviewer legs died on execution budgets. Neither was silently replaced, and the arbitration proceeded on the surviving evidence with the gap stated.
- **Reject with reasons.** The strongest single finding of wave 1 was wrong because the reviewer lacked one fact about local transcripts. Recording that rejection is what stops it being re-litigated every session.
