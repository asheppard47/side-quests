---
version: "1.0.0"
schema_version: 2
title: "Harness Adapters — Route-by-Harness Design"
doc_type: detail
parent: docs/design/INDEX.md
last_updated: 2026-09-12
last_audit: 2026-08-20
audit_status: needs-review
domain: docs
triggers:
  - "harness adapter"
  - "route by harness"
  - "codex sessions"
  - "grok sessions"
  - "gemini cli sessions"
---
# Harness Adapters — Route-by-Harness Design

**Every major agent CLI persists a local session record rich enough to grade, and the router detects the harness from the file's own shape — never from a user flag.** This is the design for extending Terminally Cooked beyond Claude Code without weakening the zero-upload contract: each adapter reads local files only and normalizes them into the ten-observable ingestion contract that `analyze()` already consumes. Advisory sources: each vendor's own frontier model was asked about its own harness (2026-08-20); Codex answers were verified against a locally installed CLI, Grok answers carry source citations into the public repo, Gemini answers are schema-level with UNVERIFIED markers preserved.

## The ingestion contract

An adapter must produce, per session: (1) ordered tool invocations paired to results with a success flag, (2) human turns distinguishable from tool results, (3) event timestamps, (4) one complete session with a stable ID — plus, when available: model and effort per turn, token usage, permission/approval mode, compaction events, test output paired with its command, and delegation markers.

One contract change came out of this review: the success flag becomes a **tri-state** (`true | false | null`), because Codex rollouts do not guarantee a universal error boolean on tool outputs. `null` results count toward neither streaks nor spirals.

## Detection table (route by harness)

| Harness | Session location | Detect by |
|---|---|---|
| Claude Code | `~/.claude/projects/<proj>/<uuid>.jsonl` | flat JSONL whose records carry `message.content[]` with `tool_use`/`tool_result` and `isSidechain` fields |
| Codex CLI | `~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl` (archived: `~/.codex/archived_sessions/`) | envelope records `{timestamp, type, payload}` with types `session_meta` / `turn_context` / `response_item` / `event_msg`; filename prefix `rollout-` |
| Grok CLI | `~/.grok/sessions/<url-encoded-cwd>/<uuidv7>/` — a **directory**, not a file | dir containing `summary.json` + `updates.jsonl` (and usually `events.jsonl`); `$GROK_HOME` overrides root |
| Gemini CLI | `~/.gemini/tmp/<project-hash>/chats/session-<ts>-<hash>.jsonl` | a sniffed record contains `sessionId` and `projectHash`; full records can be interleaved with `$set` patches |

Detection is content-first (sniff the schema), path-second (the default roots above), and never trusts extension alone.

## Per-harness observable fit

| Observable | Codex CLI | Grok CLI | Gemini CLI |
|---|---|---|---|
| Tool calls + results | pair by `payload.call_id`; success is **tri-state** (derive from exit codes/status; else `null`) | `events.jsonl` `tool_started`/`tool_completed` with an explicit `outcome` enum (`success`/`error`/`permission_rejected`/…) | `tool_use` / `tool_result` records, error status on result |
| Human turns | `event_msg.user_message` (dedupe against `response_item.message` role=user) | ACP `updates.jsonl` + `interjected` events | `type: "user"` records |
| Timestamps | top-level `timestamp` on every record | `ts` RFC3339 in `events.jsonl` | top-level `timestamp` |
| Session unit + ID | one rollout file; `session_meta.payload.session_id` (validate against filename UUID) | one directory; UUIDv7 dir name = `session_id` | one file; `session_id` in the metadata line |
| Model + effort | **per-turn** `turn_context.payload.model` and `.effort` — richer than Claude Code | `turn_started.model_id`; effort NOT FOUND | model in metadata; effort UNVERIFIED |
| Tokens | `event_msg.token_count` → `last_token_usage` (incl. cached + reasoning tokens) | `turn_completed.usage` (`inputTokens`, `cachedReadTokens`, `reasoningTokens`, `costUsdTicks`) | `message_update` / result frames |
| Permission / YOLO | `turn_context.payload.approval_policy` + `sandbox_policy` — YOLO only from the explicit dangerous combination, never `approval=never` alone | **first-class**: `turn_started.yolo_mode` boolean, `yolo_toggled`, `permission_resolved` decisions | global settings; per-turn UNVERIFIED |
| Compaction | top-level `compacted` record | `compaction_checkpoints/` dir | UNVERIFIED |
| Test output pairing | via `call_id`; apply our test-shaped-command gate | derivable from tool results; same gate | derivable from shell tool pairs; same gate |
| Delegation | `event_msg.sub_agent_activity`, `thread_spawn_edges` | **first-class**: `session_relationship: primary/subagent`, `subagents/` dir, child sessions are ordinary dirs | subagent-scoped records in-stream |

Notable: Grok's harness records more of our comedy observables natively than Claude Code's own transcript (a literal `yolo_mode` boolean), and Codex carries per-turn effort, which Claude Code only exposes per-record.

## Adapter interface

```
detect(path)        -> HarnessId | None          # content sniff, then path shape
list_sessions(root) -> [SessionRef]              # harness-specific walk
read(ref)           -> Iterator[NormalizedEvent] # feeds the 10-observable contract
```

`analyze()` stays harness-agnostic; the card's identity tuple (ruling D12) already carries the adapter name, so cross-harness cards are visibly different games. Per-harness quirks live entirely inside the adapter: Codex's duplicate user-message streams (choose one canonical source), Grok's directory-per-session layout and in-place rewind truncation, Gemini's project-hash directory naming.

## Shared gotchas the reviewers flagged

- **Every format is internal and version-dependent.** No harness publishes its session log as a contract. Adapters need fixtures per observed version and must fail open (skip what they can't parse) — the same posture the Claude Code parser already takes.
- **Privacy is worse elsewhere.** Grok transcripts can contain full tool stdout and file contents; Codex rollouts include patch bodies. The allowlist boundary does all the protecting, exactly as designed — adapters widen what is *read*, never what is *rendered*.
- **Mid-turn kills leave incomplete records** (Grok flushes usage only at `turn_completed`; Codex marks aborted turns). Adapters should grade what is present and mark the session incomplete rather than invent closure.
- **Name collisions**: the xAI `grok` CLI is not the community `superagent-ai/grok-cli`; detection must key on schema, not the word "grok" in a path.

## Status

**Implemented 2026-08-20** in `harness_adapters.py` (all four adapters + detection), with `analyze()` refactored into a harness-agnostic event consumer. Every schema was re-verified against real local session stores before coding, which corrected two advisory claims: Codex compaction is a top-level `compacted` record (not only `event_msg.context_compacted`), and Gemini files begin with a `sessionId/projectHash/kind` header followed by full-record lines interleaved with `$set` patches (not a `session_metadata` typed record). Gemini message records repeat with the same id as tool calls progress, so the adapter dedupes tool calls by call id. Cross-harness smoke: real Codex, Grok, Gemini and Claude Code sessions all grade; Codex sessions surface tri-state unknowns on the card (`?N unknown`); the adapter name is stamped in the card's provenance line per ruling D12.

Known v1 simplifications, on purpose: the Grok adapter reads `events.jsonl` + `updates.jsonl` only (no `chat_history.jsonl`) and emits a human turn per `turn_started`. Command text for Doom Loop comes from `updates.jsonl` `rawInput.command` when present; test tallies fail open because `tool_completed` carries no stdout. Usage is the last `turn_completed` snapshot (`inputTokens` already includes cache — same Codex lesson). The Grok recompute stamp frames each file name and length before its bytes. The Gemini adapter treats statuses outside its map as unknown. Auto-pick behavior, candidate limits, invoker uncertainty, and the Codex archive omission are owned by [engineering/architecture.md](../engineering/architecture.md#auto-pick-selection-and-limits). Full advisory transcripts were session-scratchpad artifacts; this doc is the durable format record.
