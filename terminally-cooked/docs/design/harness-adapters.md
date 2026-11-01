---
version: "1.0.0"
schema_version: 2
title: "Harness Adapters — Route-by-Harness Design"
doc_type: detail
parent: docs/design/INDEX.md
last_updated: 2026-11-01
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

## Canonical tool classes

Adapters never pass a raw tool name on. Each `tool_call` event carries a display `name` from the per-harness `KNOWN_TOOLS` allowlist (`mcp__server__tool` becomes `MCP` with no server name; anything unlisted becomes `Other`) and one canonical `cls`. Modifiers read only the class, so a Codex plan followed by `apply_patch` is an edit, not "All Plan No Game".

| Class | Claude Code | Codex | Grok | Gemini CLI |
|---|---|---|---|---|
| `shell` | Bash | shell, shell_command, exec_command, local_shell, exec | run_terminal_command, shell, bash | run_shell_command |
| `read` | Read, NotebookRead | — (reads go through the shell) | read_file | read_file, read_many_files |
| `edit` | Edit, MultiEdit, Write, NotebookEdit | apply_patch | edit_file, write_file, create_file | write_file, replace, edit |
| `agent` | Agent, Task | spawn_agent | — | — |
| `ask` | AskUserQuestion | request_user_input(_async) | — | — |
| `plan` | ExitPlanMode, EnterPlanMode, TodoWrite | update_plan | — | write_todos |
| `other` | every other listed built-in, MCP tools, unknown names | | | |

`command` is set only for `shell`-class calls, so a Codex `apply_patch` body is never mistaken for a command. A blank cell means the harness has no recognized tool of that class; its modifiers stay unawarded rather than guessed.

## Session ids

The card id comes only from an id-shaped name: a Claude `<uuid>.jsonl` stem, the UUID suffix of a Codex `rollout-<ts>-<uuid>.jsonl`, the 8-hex suffix of a Gemini `session-<ts>-<8hex>.jsonl` (the first 8 characters of its `sessionId`, so a full Gemini session UUID also finds the file), or a Grok `<uuid>/` directory. Any other file or directory name is user-chosen text and is replaced on the card and in output filenames by the transcript-hash prefix.

Identity is separate from that display label. Invoker checks compare the live session id against the id in the name given, the id in the resolved target's name (a symlink alias is followed), and the id the transcript states about itself: Claude record `sessionId`, Codex `session_meta` `id`/`session_id`, the Gemini header `sessionId`, and Grok `summary.json` `info.id`. A renamed copy is therefore still recognized (`harness_adapters.identity_ids`).

## Normalization rules (v0.6)

- **Shapes**: discriminators (`type`, `role`, `sessionUpdate`) and correlation ids (tool_use ids, call ids) must be strings before any membership test or dict use; any other shape is skipped at the adapter, never left to crash the grader.
- **Timing**: every record with a string timestamp emits a timing-only `tick`, so a deduplicated Gemini repeat or a Codex final assistant message still extends the session. Ticks set first and last timestamps and window boundaries and nothing else; they never touch counts, streaks or Night Shift.
- **Non-object records** (`[]`, `null`, a bare string) and non-object nested fields are skipped everywhere, including Codex `session_meta` sniffing during discovery.
- **Claude Code**: a compaction summary record emits only the compaction event. A user record that carries `tool_result` blocks is not a human turn, even when the harness attached `<system-reminder>` text to it; one human event per record otherwise.
- **Codex outcomes** come from the tool-output envelope, never from stdout: the header lines before `Output:` carrying `Exit code: N` (shell, apply_patch) or `Process exited with code N` (exec_command), or the older JSON `{"output", "metadata": {"exit_code"}}`. `Script completed`/`Script failed` (code-mode `exec`) and `Process running with session ID` stay unknown. Envelope shapes rechecked against local rollouts on 2026-11-01.
- **Codex user turns**: when a rollout has `event_msg.user_message` records, those are the human turns; otherwise role-user `response_item` messages count, skipping only known injected context: `# AGENTS.md instructions` and the tags `<environment_context>`, `<user_instructions>`, `<heartbeat>`, `<external_codex_apps_open_page>`, `<in-app-browser-context>`, `<recommended_plugins>`, `<subagent_notification>` and `<turn_aborted>` (markers from local rollouts, 2026-11-01). Any other text is a person's turn, tag-wrapped or not, including `<send_user_message_question_reply>` and `<realtime_delegation>`, which carry the user's own answers.
- **Gemini**: a message repeated under the same id is a snapshot; its model and final token counts count once.
- **Grok**: tool-result text comes from `updates.jsonl` `tool_call_update` (`rawOutput.output`/`stdout`, else the content text blocks), so test tallies and Overloaded can fire; a call with no captured output has empty text.

## Shared gotchas the reviewers flagged

- **Every format is internal and version-dependent.** No harness publishes its session log as a contract. Adapters need fixtures per observed version and must fail open (skip what they can't parse) — the same posture the Claude Code parser already takes.
- **Privacy is worse elsewhere.** Grok transcripts can contain full tool stdout and file contents; Codex rollouts include patch bodies. The allowlist boundary does all the protecting, exactly as designed — adapters widen what is *read*, never what is *rendered*.
- **Mid-turn kills leave incomplete records** (Grok flushes usage only at `turn_completed`; Codex marks aborted turns). Adapters should grade what is present and mark the session incomplete rather than invent closure.
- **Name collisions**: the xAI `grok` CLI is not the community `superagent-ai/grok-cli`; detection must key on schema, not the word "grok" in a path.

## Status

**Implemented 2026-08-20** in `harness_adapters.py` (all four adapters + detection), with `analyze()` refactored into a harness-agnostic event consumer. Every schema was re-verified against real local session stores before coding, which corrected two advisory claims: Codex compaction is a top-level `compacted` record (not only `event_msg.context_compacted`), and Gemini files begin with a `sessionId/projectHash/kind` header followed by full-record lines interleaved with `$set` patches (not a `session_metadata` typed record). Gemini message records repeat with the same id as tool calls progress, so the adapter dedupes tool calls by call id and counts each message's model and tokens once. Cross-harness smoke: real Codex, Grok, Gemini and Claude Code sessions all grade; Codex sessions surface tri-state unknowns on the card (`?N unknown`); the adapter name is stamped in the card's provenance line per ruling D12.

Known simplifications, on purpose: the Grok adapter reads `events.jsonl` + `updates.jsonl` (and the presence of `compaction_checkpoints/`), not `chat_history.jsonl`, and emits a human turn per `turn_started`. Command and output text for Doom Loop and test tallies come from `updates.jsonl` when present. Usage is the last `turn_completed` snapshot (`inputTokens` already includes cache — same Codex lesson). The Grok recompute stamp frames each file's relative name and length before its bytes and covers the checkpoint entries. The Gemini adapter treats statuses outside its map as unknown. Auto-pick behavior, candidate limits, invoker uncertainty, and the Codex archive omission are owned by [engineering/architecture.md](../engineering/architecture.md#auto-pick-selection-and-limits). Full advisory transcripts were session-scratchpad artifacts; this doc is the durable format record.
