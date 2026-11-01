---
version: "1.0.0"
schema_version: 2
title: "Decision Log"
doc_type: detail
parent: docs/product/INDEX.md
last_updated: 2026-11-01
last_audit: 2026-08-19
audit_status: needs-review
domain: docs
triggers:
  - "llm grader decisions"
  - "why no leaderboard"
  - "killed lineages"
---
# Decision Log

**Every ruling that constrains this product, with its date, its owner, and the evidence behind it.** Rulings marked CLOSED are not open for casual reversal; reopening one requires new evidence and a new dated entry, not a preference. Evidence sits in [research/review-ledgers.md](../research/review-ledgers.md) and the workshop X-research capsule.

## Closed rulings

| # | Date | Ruling | Basis |
|---|---|---|---|
| D1 | 2026-08-18 | **Rhythm-game predecessor archived.** A slow-classical rhythm game on the same diff aesthetic reached approved-core-loop stage and was archived for scope: chart authoring plus a real-time engine is a full game build. | Owner scope call |
| D2 | 2026-08-18 | **No sale of session-derived training data.** CLOSED — three independently fatal problems: contributors cannot license employer work product; "synthetic" derivation neither cures rights nor prevents leakage; no buyer exists, since labs hold better first-party traces with legal cover. | Both wave-1 reviewers, unanimous |
| D3 | 2026-08-18 | **Zero upload is permanent, not a V1 stage.** Deferred collection would be a purpose change that poisons consent and reads as malware to corporate security. Any corpus product must be separately named with fresh consent. | Wave-1 reviewers |
| D4 | 2026-08-18 | **Data layer reshaped to marketing and recognition only**, operating on card-level allowlisted fields, with submission as a separate explicit human act. | Owner, after D2 |
| D5 | 2026-08-18 | **No hosted leaderboard.** Self-reported local telemetry cannot be ranked honestly; ranking also invites farming. Corroborated externally: an internal AI-coding leaderboard at a large company reportedly produced "tokenmaxxing" of useless tasks before being scrapped. | Wave-1 reviewers + X research |
| D6 | 2026-08-18 | **Condition multipliers carry no fairness claim.** Model, effort, and compaction bonuses were dropped as ranked adjustments; conditions are descriptive only. | Wave-1 reviewers |
| D7 | 2026-08-18 | **Session unit frozen to one Claude Code session UUID.** Cross-tool ingestion and cross-session comparison are out of scope until each tool's unit can be mapped with evidence. | Wave-1 reviewers |
| D8 | 2026-08-19 | **Multipliers are reserved for serialized success; everything else adds flat.** Sustained error-free work scores superlinearly. | Owner directive, implemented as scoring v0.4 |
| D9 | 2026-08-19 | **Badge names are rendered by the UI, not painted into the art.** Baked-in nameplates degrade to noise at 32 px and cannot be made consistent across models. | Game-industry icon review |
| D10 | 2026-08-19 | **Art direction: painterly, luminous, textless.** Terminal-green/cyber palettes, neon "electric" grading, and photographic HDR vocabulary are all rejected. | Owner art direction |
| D11 | 2026-08-19 | **Blind A/B, one vote per person, outside parties.** Both models render identical prompts; votes are collected as native Telegram polls in a real developer group rather than solo judgment. | Owner; both review waves flagged solo comedy judgment as a defect |
| D12 | 2026-08-20 | **Scoring standard: one complete native session is the canonical unit.** No rolling lookback (invites boundary slicing), no best-session ladder (rewards grinding). Comparability rides the identity tuple — scoring version, division (blitz/sprint/long haul), delegation class, duration, recompute stamp — never the bare number. | Publish-review wave (Sol #10-11; Flash's normalized-rating proposal partially adopted as divisions-as-labels, rejected as a second score) |
| D13 | 2026-08-20 | **Subagent work is never imputed.** Sessions with subagent calls print a delegation class ("internals not graded"). Weighting Agent calls by duration or tokens fabricates precision about invisible work. | Publish-review wave (Sol #3 over Flash #2) |
| D14 | 2026-08-20 | **Share-to-X is caption-to-clipboard plus a blank composer.** No prefilled intent URLs and no upload APIs — both transmit the score before the user posts. The `--share` flag copies a caption from allowlisted fields and opens the composer; the user pastes. | Publish-review wave (Sol #16 over Flash #8) |
| D15 | 2026-08-20 | **Anti-cheat posture for publication: "self-attested, reproducible locally, not authenticated."** The recompute stamp stays; HMAC slugs with a public salt were rejected as forgeable theater. Honest reproduction is made cheap (published source, tagged releases) rather than pretending provenance. | Publish-review wave (Sol #12-13; Flash #7 rejected) |
| D16 | 2026-08-20 | **V1 public claim was Claude Code main-session transcripts.** Other tools were future ingestion adapters, each needing its own session-unit mapping. Amended by D17 the same day once vendor-model adapter designs landed. | Publish-review wave (both reviewers) |
| D17 | 2026-08-20 | **Four harnesses, one event contract.** Claude Code, Codex, Grok, and Gemini CLI are auto-detected from file shape. Cards stamp the adapter. Cross-harness scores are different games and say so. Unknown tool outcomes never fill a "clean" window. | Vendor-model adapter wave + validation repairs |
| D18 | 2026-08-20 | **Public MIT source is the anti-cheat.** Scoring is self-attested and reproducible locally (D15). The repo is public so anyone can recompute a card. Badge PNGs ship in the clone and are inlined as data URIs — grading must never hit the network. | Owner publication directives |
| D19 | 2026-08-20 | **Public name is Terminally Cooked — An AI Coding Session Roast.** GitHub slug `terminally-cooked`. Working title LLM Grader retired (collides with a student-work grader and claims measurement). Promptmortem rejected on uniqueness (`promptmortem.ai` is the same audience). RoastDiff rejected as roast-your-diffs category confusion. Council record: local `council_llm_grader_name_20260820.md`. | Council (sol × 3 personae) + naming-playbook collision screen |
| D20 | 2026-11-01 | **Repo becomes `asheppard47/side-quests`; this product moves to `terminally-cooked/`.** Renamed in place (history kept, old URLs redirect) so other joke projects can sit beside it. D5 and binding constraint 3 still cover people's sessions: no leaderboard of users ever. The sibling `desk-bench/` ranks models on a fixed fake desktop, which is a different game and does not reverse D5. | Owner |
| D21 | 2026-11-01 | **Scoring v0.6: review-wave repairs ship as one versioned change.** Card ids come only from id-shaped names (else the transcript hash); tool names render only as allowlisted labels, with MCP servers never named; control characters are stripped from every rendered string. The invoker is excluded by id when the harness exposes one, explicit targets matching it are refused, and without an id the exclusion is a disclosed heuristic over the unfiltered session list. The PNG renderer runs Chrome with network-off flags and both pages carry a CSP; the claim is narrowed to those controls. Tallies, test-runner detection, Codex outcomes, adapter normalization, harness-neutral tool classes, completed windows, the recompute stamp (both modules, every Grok input, explicit zone) and output-file safety were corrected in the same bump. A pre-push review (Sol) added, inside the same version: invoker identity from resolved paths and transcript ids, vendor-shaped model ids and known effort levels only, session-first CLI with extension-checked destinations, lone-runner tallies, typed discriminators, timing ticks, exact Codex context markers, and fail-closed no-force publication. Doom Loop keeps its catalog reset rule (non-shell tools do not reset); Linux clipboard for `--share` declined as out of scope. | Owner approval of the Astra and Argon code reviews and the Sol pre-push verification ([review ledger wave 6](../research/review-ledgers.md#wave-6--code-review-2026-11-01)) |

## Open questions

| Question | Status | Blocking |
|---|---|---|
| Which model's art ships per badge | Round 1 closed 2026-08-20; winners in `assets/badges/` — sample size is three voters, 2–1 splits are thin | Not blocking ship |
| Persistent badges and a local history file | Deliberately unbuilt; audience research says session-scoped roasts are welcome and lifetime counters are mocked | Needs a history schema allowlist + idempotency tests first |
| Public display name vs repo slug | **Closed 2026-08-20 (D19):** Terminally Cooked — An AI Coding Session Roast; GitHub `asheppard47/terminally-cooked`. Working title LLM Grader retired. | — |
| Marketing and recognition lane | Designed as card-level only; waits for users | Real users |
| Invoker exclusion under uncertain identity | Narrowed by D21: id-based exclusion and refusal are enforced, and the no-id fallback is a disclosed heuristic (newest per harness and in this project). Still open: a live session that is not the newest of its harness, and Gemini CLI, which exposes no recognized id. | A Gemini session-id variable, or an owner call on abstaining when no id is present |
| Codex archived-session discovery | `~/.codex/archived_sessions/` is documented but not enumerated by `list_sessions`. | Add discovery and fixtures, or remove the location from supported auto-pick scope |
| Candidate coverage outside today | Auto-pick parses at most 20 sessions in total, today's first (D21). A busy day can therefore crowd out the rest of the week. | Define and test a different bounded strategy if whole-week selection is required |

## Reversal conditions

D2, D3 and D5 are the load-bearing ones. D2 and D3 reverse only with a specialist legal review plus a named buyer and a consent regime — that is a different product. D5 could reverse only if session capture became verifiable at the source (signed capture provenance), which no current tool provides.
