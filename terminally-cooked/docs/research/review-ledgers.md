---
version: "1.0.0"
schema_version: 2
title: "External Review Ledgers"
doc_type: detail
parent: INDEX.md
last_updated: 2026-08-19
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

## Practices worth keeping

- **Review the plan before spending.** The X research plan was reviewed before any metered call; the reviewers rewrote the queries, added anti-promotion filters, and forced observability tagging at collection time. That pass prevented an entire wasted research budget.
- **Report failed legs honestly.** Two reviewer legs died on execution budgets. Neither was silently replaced, and the arbitration proceeded on the surviving evidence with the gap stated.
- **Reject with reasons.** The strongest single finding of wave 1 was wrong because the reviewer lacked one fact about local transcripts. Recording that rejection is what stops it being re-litigated every session.
