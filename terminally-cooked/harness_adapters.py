#!/usr/bin/env python3
"""Harness adapters: route-by-harness session ingestion for Terminally Cooked.

Each adapter reads LOCAL files only and normalizes a session into the shared
event contract consumed by grade_session.analyze(). Detection is
content-first (sniff the schema), path-second, and never trusts a flag.
Design: docs/design/harness-adapters.md. Schemas verified against real local
session stores on 2026-08-20 (Codex and Grok result envelopes rechecked
2026-11-01); anything absent in a harness simply never emits its event
(detectors fail open). Records that are not JSON objects are skipped.

Discriminators (`type`, roles) and correlation ids (tool_use / call ids) are
validated as strings before any membership test or dict use, so an
unsupported shape is skipped here rather than crashing the grader.

Normalized events (dicts; every event may carry "ts" ISO-8601):
  {"kind": "tick"}                                    timing only: one per
        record with a string timestamp, so duration and windows see the true
        last timestamp even when deduplication or silence drops the record
  {"kind": "human"}                                   user turn
  {"kind": "interrupt"}                               user interrupted the agent
  {"kind": "tool_call", "id", "name", "cls", "command"}
        name: allowlisted display label (tool_label), never the raw name
        cls:  one of TOOL_CLASSES; command: shell-class calls only, else None
  {"kind": "tool_result", "id", "success", "text"}    success: True|False|None
  {"kind": "model", "model", "effort"}                either field may be None
  {"kind": "usage", "input", "output"}                token counts
  {"kind": "permission", "mode"}                      "bypass" | "plan"
  {"kind": "compaction"}
"""
import json
import os
import re
from pathlib import Path

CLAUDE_INTERRUPT = "[Request interrupted"

TOOL_CLASSES = ("shell", "read", "edit", "agent", "ask", "plan", "other")

# Built-in tool names per harness -> canonical class. The name itself is the
# card label; anything not listed renders as "MCP" (mcp__server__tool) or
# "Other", so a transcript can never put an arbitrary string on a card.
KNOWN_TOOLS = {
    "claude-code": {
        "Bash": "shell", "Read": "read", "NotebookRead": "read",
        "Edit": "edit", "MultiEdit": "edit", "Write": "edit", "NotebookEdit": "edit",
        "Agent": "agent", "Task": "agent", "AskUserQuestion": "ask",
        "ExitPlanMode": "plan", "EnterPlanMode": "plan", "TodoWrite": "plan",
        "Glob": "other", "Grep": "other", "LS": "other", "WebFetch": "other",
        "WebSearch": "other", "BashOutput": "other", "KillShell": "other",
        "KillBash": "other", "Skill": "other", "SlashCommand": "other",
        "ToolSearch": "other", "TaskOutput": "other", "TaskStop": "other",
        "Monitor": "other",
    },
    "codex": {
        "shell": "shell", "shell_command": "shell", "exec_command": "shell",
        "local_shell": "shell", "container.exec": "shell", "exec": "shell",
        "write_stdin": "other", "apply_patch": "edit", "update_plan": "plan",
        "request_user_input": "ask", "request_user_input_async": "ask",
        "spawn_agent": "agent", "send_message": "other", "followup_task": "other",
        "wait": "other", "wait_agent": "other", "list_agents": "other",
        "close_agent": "other", "view_image": "other", "web_search": "other",
        "js": "other",
    },
    "grok": {
        "run_terminal_command": "shell", "shell": "shell", "bash": "shell",
        "read_file": "read", "edit_file": "edit", "write_file": "edit",
        "create_file": "edit", "grep": "other", "list_dir": "other",
        "search_tool": "other", "web_search": "other",
    },
    "gemini": {
        "run_shell_command": "shell", "read_file": "read", "read_many_files": "read",
        "write_file": "edit", "replace": "edit", "edit": "edit", "write_todos": "plan",
        "glob": "other", "search_file_content": "other", "grep": "other",
        "list_directory": "other", "web_fetch": "other", "google_web_search": "other",
        "save_memory": "other",
    },
}


def tool_label(harness, raw):
    """(display label, canonical class) for a transcript tool name."""
    if isinstance(raw, str):
        cls = KNOWN_TOOLS.get(harness, {}).get(raw)
        if cls:
            return raw, cls
        if raw.startswith("mcp__"):
            return "MCP", "other"
    return "Other", "other"


def _dict(v):
    return v if isinstance(v, dict) else {}


def _list(v):
    return v if isinstance(v, list) else []


def _num(v):
    if isinstance(v, bool):
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    return 0


def _str(v):
    return v if isinstance(v, str) and v else None


def _id(v):
    """A correlation id usable as a dict key: a non-empty string, else None."""
    return v if isinstance(v, str) and v else None


def _tick(ts):
    return {"kind": "tick", "ts": ts}


def _iter_jsonl(path):
    """JSON objects only: malformed lines and non-object records are skipped."""
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, RecursionError):
                continue
            if isinstance(rec, dict):
                yield rec


def _text(content):
    """Flatten a string / list-of-text-blocks content field."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(x["text"] for x in content
                        if isinstance(x, dict) and isinstance(x.get("text"), str))
    return ""


# ---------------------------------------------------------------- detection

CODEX_ENVELOPE = {"session_meta", "turn_context", "response_item", "event_msg",
                  "compacted", "world_state"}
CLAUDE_TYPES = {"last-prompt", "mode", "permission-mode", "user", "assistant",
                "attachment", "summary", "file-history-snapshot"}


def detect_harness(path, any_suffix=False):
    """Return 'claude-code' | 'codex' | 'grok' | 'gemini' | None.

    Content-first: sniff up to the first few parseable records (BOM- and
    blank-line-tolerant), then fall back to home-directory shape. Store
    discovery only considers `.jsonl` files; an explicit target or an
    identity check passes any_suffix=True so a renamed transcript is still
    recognized by its content."""
    p = Path(path)
    if p.is_dir():
        if (p / "summary.json").exists() and (
                (p / "events.jsonl").exists() or (p / "updates.jsonl").exists()):
            return "grok"
        return None
    if p.suffix != ".jsonl" and not any_suffix:
        return None
    records = []
    try:
        with p.open(encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except (json.JSONDecodeError, RecursionError):
                    continue
                if len(records) >= 5:
                    break
    except OSError:
        return None
    for first in records:
        if not isinstance(first, dict):
            continue
        rtype = _str(first.get("type"))
        if rtype in CODEX_ENVELOPE and "payload" in first:
            return "codex"
        if "sessionId" in first and "projectHash" in first:
            return "gemini"
        # Claude Code's giveaway is its record vocabulary or its home.
        if "parentUuid" in first or rtype in CLAUDE_TYPES:
            return "claude-code"
    parent = str(p.parent)
    if ".claude" in parent:
        return "claude-code"
    if ".gemini" in parent:
        return "gemini"
    if ".codex" in parent:
        return "codex"
    return None


UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
TRAILING_UUID_RE = re.compile(r"-(" + UUID_RE.pattern + r")$", re.I)
GEMINI_NAME_RE = re.compile(r"^session-.+-([0-9a-f]{8})$", re.I)


def session_label(path):
    """The session id a record's own name carries, or None.

    Only id-shaped names count: a Claude <uuid>.jsonl stem, a Codex
    rollout-<ts>-<uuid> suffix, a Gemini session-<ts>-<8hex> suffix, or a
    Grok <uuid> directory. Any other name is user-chosen text and must never
    reach a card or an output filename."""
    p = Path(path)
    if p.is_dir():
        name = p.resolve().name
        return name.lower() if UUID_RE.fullmatch(name) else None
    stem = p.stem
    if UUID_RE.fullmatch(stem):
        return stem.lower()
    m = GEMINI_NAME_RE.match(stem)
    if m:
        return m.group(1).lower()
    m = TRAILING_UUID_RE.search(stem)
    if m and stem.startswith("rollout-"):
        return m.group(1).lower()
    return None


def transcript_ids(path, harness=None, limit=50):
    """Session ids a transcript states about itself, lowercased: Claude record
    `sessionId`, Codex `session_meta` id, Gemini header `sessionId`, Grok
    `summary.json` info.id. Unreadable or unsupported shapes give none."""
    p = Path(path)
    harness = harness or detect_harness(p, any_suffix=True)
    found = set()
    try:
        if harness == "grok":
            info = _dict(_dict(json.loads((p / "summary.json").read_text(
                encoding="utf-8", errors="replace"))).get("info"))
            found.add(_id(info.get("id")))
        elif harness == "codex":
            meta = _codex_meta(p)
            found.update((_id(meta.get("id")), _id(meta.get("session_id"))))
        elif harness in ("claude-code", "gemini") or (harness is None and p.is_file()):
            for n, rec in enumerate(_iter_jsonl(p)):
                sid = _id(rec.get("sessionId"))
                found.add(sid)
                # one id per file in every local Claude store (2026-11-01 check)
                if sid or harness == "gemini" or n >= limit:
                    break
    except (OSError, ValueError, RecursionError):
        pass
    return {i.strip().lower() for i in found if i and i.strip()}


def identity_ids(path):
    """Every id that can establish which session a path really is: the id in
    the name it was given, the id in its resolved target's name, and the ids
    the transcript states. Identity only; never displayed."""
    p = Path(path)
    try:
        real = p.resolve()
    except (OSError, RuntimeError):
        real = p
    ids = {session_label(p), session_label(real)} | transcript_ids(real)
    return {i for i in ids if i}


def session_identity(path, harness):
    """(session_id or None, files-to-hash). Grok hashes every file that feeds
    the score: events.jsonl, updates.jsonl, and compaction_checkpoints/
    entries (their presence awards Lost the Tapes)."""
    p = Path(path)
    label = session_label(p)
    if harness == "grok":
        files = [p / n for n in ("events.jsonl", "updates.jsonl") if (p / n).exists()]
        cc = p / "compaction_checkpoints"
        if cc.is_dir():
            files.extend(sorted(cc.iterdir()))
        return label, files or [p]
    return label, [p]


# ---------------------------------------------------------------- claude-code

def _claude_events(path):
    for rec in _iter_jsonl(path):
        ts = rec.get("timestamp")
        if isinstance(ts, str):
            yield _tick(ts)
        rtype = _str(rec.get("type"))
        if rec.get("isCompactSummary"):
            yield {"kind": "compaction", "ts": ts}
            continue
        if rtype == "permission-mode":
            mode = str(rec.get("permissionMode", ""))
            if mode == "bypassPermissions":
                yield {"kind": "permission", "mode": "bypass", "ts": ts}
            elif mode == "plan":
                yield {"kind": "permission", "mode": "plan", "ts": ts}
        elif rtype == "assistant":
            msg = _dict(rec.get("message"))
            model = _str(msg.get("model"))
            if model and not model.startswith("<"):
                yield {"kind": "model", "model": model,
                       "effort": _str(rec.get("effort")), "ts": ts}
            usage = _dict(msg.get("usage"))
            if usage:
                yield {"kind": "usage", "ts": ts,
                       "input": (_num(usage.get("input_tokens"))
                                 + _num(usage.get("cache_read_input_tokens"))
                                 + _num(usage.get("cache_creation_input_tokens"))),
                       "output": _num(usage.get("output_tokens"))}
            for block in _list(msg.get("content")):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    label, cls = tool_label("claude-code", block.get("name"))
                    cmd = None
                    if cls == "shell":
                        c = _dict(block.get("input")).get("command")
                        cmd = c.strip() if isinstance(c, str) else None
                    yield {"kind": "tool_call", "id": _id(block.get("id")), "name": label,
                           "cls": cls, "command": cmd, "ts": ts}
        elif rtype == "user":
            content = _dict(rec.get("message")).get("content")
            if isinstance(content, str):
                yield {"kind": "human", "ts": ts}
                if CLAUDE_INTERRUPT in content:
                    yield {"kind": "interrupt", "ts": ts}
                continue
            blocks = [b for b in _list(content) if isinstance(b, dict)]
            if not blocks:
                continue
            has_result = any(b.get("type") == "tool_result" for b in blocks)
            interrupted = any(b.get("type") == "text" and isinstance(b.get("text"), str)
                              and CLAUDE_INTERRUPT in b["text"] for b in blocks)
            # text riding along with tool results is harness-injected
            # (system reminders), not a person typing
            if not has_result or interrupted:
                yield {"kind": "human", "ts": ts}
            if interrupted:
                yield {"kind": "interrupt", "ts": ts}
            for block in blocks:
                if block.get("type") == "tool_result":
                    yield {"kind": "tool_result", "id": _id(block.get("tool_use_id")),
                           "success": not block.get("is_error"),
                           "text": _text(block.get("content")), "ts": ts}


# ---------------------------------------------------------------- codex

CODEX_EXIT_LINE = re.compile(r"^(?:Exit code:|Process exited with code)\s*(-?\d+)$")


def _codex_success(output):
    """Outcome from the tool-output envelope only, never from stdout.

    Supported envelopes (observed in local rollouts): a header block of
    `Label: value` lines ending at an `Output:` line, carrying `Exit code: N`
    (shell, apply_patch) or `Process exited with code N` (exec_command); and
    the older JSON string `{"output": ..., "metadata": {"exit_code": N}}`.
    Without an `Output:` line only the first line is header. Anything else,
    including a still-running process, is unknown."""
    if isinstance(output, list):
        texts = [b["text"] for b in output
                 if isinstance(b, dict) and isinstance(b.get("text"), str)]
        output = texts[0] if texts else ""
    if not isinstance(output, str):
        return None
    if output.lstrip().startswith("{"):
        try:
            env = json.loads(output)
        except (json.JSONDecodeError, RecursionError):
            env = None
        if isinstance(env, dict):
            code = _dict(env.get("metadata")).get("exit_code")
            if isinstance(code, int) and not isinstance(code, bool):
                return code == 0
            return None
    lines = [ln.strip() for ln in output.split("\n")]
    end = next((i for i, ln in enumerate(lines) if ln.startswith("Output:")), None)
    header = lines[:end] if end is not None else lines[:1]
    codes = [int(m.group(1)) for m in (CODEX_EXIT_LINE.match(ln) for ln in header) if m]
    if len(codes) == 1:
        return codes[0] == 0
    return None


SHELL_C_FLAGS = {"-c", "-lc", "-ic", "-lic", "-ilc"}


def _codex_command(p):
    """Extract a command string from either call shape. custom_tool_call carries
    a raw input string; function_call packs JSON arguments."""
    if isinstance(p.get("input"), str):
        return p["input"]
    args = p.get("arguments")
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
        except (json.JSONDecodeError, RecursionError):
            return None
        for key in ("command", "cmd", "script"):
            v = parsed.get(key) if isinstance(parsed, dict) else None
            if isinstance(v, str):
                return v
            if isinstance(v, list):
                parts = [str(x) for x in v]
                if len(parts) >= 3 and parts[-2] in SHELL_C_FLAGS:
                    return parts[-1]          # ["bash", "-lc", "<script>"]
                return " ".join(parts)
    return None


# Context Codex injects as role-user messages. Exact markers only, from the
# adapter doc and local rollouts (2026-11-01); any other text, tag-wrapped or
# not, is a person's turn.
CODEX_CONTEXT_TAGS = ("environment_context", "user_instructions", "heartbeat",
                      "external_codex_apps_open_page", "in-app-browser-context",
                      "recommended_plugins", "subagent_notification", "turn_aborted")
CODEX_CONTEXT_RE = re.compile(r"<(?:%s)[\s>]" % "|".join(map(re.escape, CODEX_CONTEXT_TAGS)))
CODEX_AGENTS_HEADER = "# AGENTS.md instructions"


def _codex_is_human(p):
    """A role-user message is a person's turn unless every text block is a
    known injected-context record."""
    for b in _list(p.get("content")):
        if not isinstance(b, dict):
            continue
        if b.get("type") == "input_image":
            return True
        t = b.get("text")
        if not isinstance(t, str) or not t.strip():
            continue
        t = t.lstrip()
        if t.startswith(CODEX_AGENTS_HEADER) or CODEX_CONTEXT_RE.match(t):
            continue
        return True
    return False


def _codex_has_event_user_messages(path):
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            if "user_message" not in line:
                continue
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, RecursionError):
                continue
            if (isinstance(rec, dict) and rec.get("type") == "event_msg"
                    and _dict(rec.get("payload")).get("type") == "user_message"):
                return True
    return False


def _codex_events(path):
    # Rollouts may write each user turn as event_msg.user_message AND as a
    # role-user response_item; count one stream so a turn is one human event.
    event_humans = _codex_has_event_user_messages(path)
    last_totals = None       # token_count records are cumulative snapshots:
    last_totals_ts = None    # summing per-snapshot usage double-counts turns
    for rec in _iter_jsonl(path):
        ts = rec.get("timestamp")
        if isinstance(ts, str):
            yield _tick(ts)
        rtype = _str(rec.get("type"))
        p = _dict(rec.get("payload"))
        if rtype == "compacted":
            yield {"kind": "compaction", "ts": ts}
        elif rtype == "turn_context":
            model, effort = _str(p.get("model")), _str(p.get("effort"))
            if model or effort:
                yield {"kind": "model", "model": model, "effort": effort, "ts": ts}
            sandbox = json.dumps(p.get("sandbox_policy", "")).lower()
            if p.get("approval_policy") == "never" and (
                    "danger" in sandbox or "full" in sandbox):
                yield {"kind": "permission", "mode": "bypass", "ts": ts}
            collab = _dict(p.get("collaboration_mode"))
            if collab.get("kind") == "plan":
                yield {"kind": "permission", "mode": "plan", "ts": ts}
        elif rtype == "event_msg":
            st = _str(p.get("type"))
            if st == "user_message":
                yield {"kind": "human", "ts": ts}
            elif st == "turn_aborted":
                yield {"kind": "interrupt", "ts": ts}
            elif st == "token_count":
                tot = _dict(_dict(p.get("info")).get("total_token_usage"))
                if tot:
                    last_totals, last_totals_ts = tot, ts
        elif rtype == "response_item":
            st = _str(p.get("type"))
            if st == "message" and p.get("role") == "user":
                if not event_humans and _codex_is_human(p):
                    yield {"kind": "human", "ts": ts}
            elif st in ("function_call", "custom_tool_call"):
                label, cls = tool_label("codex", p.get("name"))
                cmd = _codex_command(p) if cls == "shell" else None
                yield {"kind": "tool_call", "id": _id(p.get("call_id")), "name": label,
                       "cls": cls, "command": cmd, "ts": ts}
            elif st in ("function_call_output", "custom_tool_call_output"):
                out = p.get("output")
                yield {"kind": "tool_result", "id": _id(p.get("call_id")),
                       "success": _codex_success(out), "text": _text(out), "ts": ts}
    if last_totals:
        # input_tokens already includes cached tokens (total == input + output)
        yield {"kind": "usage", "ts": last_totals_ts,
               "input": _num(last_totals.get("input_tokens")),
               "output": _num(last_totals.get("output_tokens"))}


# ---------------------------------------------------------------- grok

GROK_OUTCOME = {"success": True, "error": False, "invalid_tool": False,
                "hook_denied": False}


def _grok_unwrap(rec):
    params = rec.get("params")
    if isinstance(params, dict):                   # raw ACP notification
        return params.get("update") or params
    return rec


def _grok_output_text(u):
    raw = _dict(u.get("rawOutput"))
    parts = [raw[k] for k in ("output", "stdout", "stderr") if isinstance(raw.get(k), str)]
    if parts:
        return "\n".join(parts)
    texts = []
    for b in _list(u.get("content")):
        inner = _dict(_dict(b).get("content"))
        if isinstance(inner.get("text"), str):
            texts.append(inner["text"])
    return "\n".join(texts) if texts else None


def _grok_updates(d):
    """One pass over updates.jsonl: command text and output per call id, and
    the last usage snapshot.

    `turn_completed.usage` is a cumulative session total (inputTokens already
    includes cachedReadTokens; totalTokens == input + output), same shape as
    Codex token_count. Summing snapshots double-counts; adding cached on top
    does it twice.
    """
    cmds, outputs, last_usage = {}, {}, None
    up = d / "updates.jsonl"
    if not up.exists():
        return cmds, outputs, last_usage
    for rec in _iter_jsonl(up):
        u = _grok_unwrap(rec)
        if not isinstance(u, dict):
            continue
        su = _str(u.get("sessionUpdate"))
        if su in ("tool_call", "tool_call_update"):
            cid = u.get("toolCallId")
            if not isinstance(cid, str):
                continue
            cmd = _dict(u.get("rawInput")).get("command")
            if isinstance(cmd, str) and cmd.strip():
                cmds[cid] = cmd.strip()
            text = _grok_output_text(u)
            if text is not None:
                outputs[cid] = text
        elif su == "turn_completed":
            usage = _dict(u.get("usage"))
            if usage:
                last_usage = usage
    return cmds, outputs, last_usage


def _grok_events(path):
    d = Path(path)
    cmds, outputs, last_usage = _grok_updates(d)
    ev = d / "events.jsonl"
    if ev.exists():
        for rec in _iter_jsonl(ev):
            ts = rec.get("ts")
            if isinstance(ts, str):
                yield _tick(ts)
            rtype = _str(rec.get("type"))
            if rtype == "turn_started":
                yield {"kind": "human", "ts": ts}
                model = _str(rec.get("model_id"))
                if model:
                    yield {"kind": "model", "model": model, "effort": None, "ts": ts}
                if rec.get("yolo_mode") is True:
                    yield {"kind": "permission", "mode": "bypass", "ts": ts}
            elif rtype == "interjected":
                yield {"kind": "interrupt", "ts": ts}
            elif rtype == "tool_completed":
                cid = rec.get("tool_call_id")
                cid = cid if isinstance(cid, str) else None
                label, cls = tool_label("grok", rec.get("tool_name"))
                outcome = rec.get("outcome")
                yield {"kind": "tool_call", "id": cid, "name": label, "cls": cls,
                       "command": cmds.get(cid) if cls == "shell" else None, "ts": ts}
                yield {"kind": "tool_result", "id": cid,
                       "success": GROK_OUTCOME.get(outcome) if isinstance(outcome, str) else None,
                       "text": outputs.get(cid, ""), "ts": ts}
    if last_usage:
        yield {"kind": "usage", "ts": None,
               "input": _num(last_usage.get("inputTokens")),
               "output": _num(last_usage.get("outputTokens"))}
    cc = d / "compaction_checkpoints"
    if cc.is_dir() and any(cc.iterdir()):
        yield {"kind": "compaction", "ts": None}


# ---------------------------------------------------------------- gemini

GEMINI_STATUS = {"success": True, "completed": True, "confirmed": True,
                 "error": False, "failed": False, "cancelled": None}


def _gemini_events(path):
    called = set()       # call ids whose tool_call was emitted
    resolved = set()     # call ids whose TERMINAL result was emitted
    anon = anon_msg = 0
    modeled = set()      # message ids whose model was emitted
    usage = {}           # message id -> final (input, output) snapshot
    for rec in _iter_jsonl(path):
        if "$set" in rec or ("sessionId" in rec and "projectHash" in rec):
            continue
        ts = rec.get("timestamp")
        if isinstance(ts, str):
            yield _tick(ts)
        rtype = _str(rec.get("type"))
        if rtype == "user":
            yield {"kind": "human", "ts": ts}
        elif rtype == "gemini":
            # records repeat with the same message id as the message and its
            # calls progress; each repeat is a snapshot, so the message
            # counts once with its final tokens
            mid = rec.get("id")
            if not isinstance(mid, (str, int)) or isinstance(mid, bool):
                anon_msg += 1
                mid = f"_anon_msg_{anon_msg}"
            model = _str(rec.get("model"))
            if model and mid not in modeled:
                modeled.add(mid)
                yield {"kind": "model", "model": model, "effort": None, "ts": ts}
            tok = _dict(rec.get("tokens"))
            if tok:
                usage[mid] = (_num(tok.get("input")) + _num(tok.get("cached")),
                              _num(tok.get("output")))
            for call in _list(rec.get("toolCalls")):
                if not isinstance(call, dict):
                    continue
                cid = call.get("id")
                if not isinstance(cid, (str, int)) or isinstance(cid, bool):
                    anon += 1
                    cid = f"_anon_{anon}"
                status = str(call.get("status") or "").lower()
                # emit the call once, and the result only on a TERMINAL status
                # ("running"/"pending" must not lock the outcome as unknown)
                if cid not in called:
                    called.add(cid)
                    label, cls = tool_label("gemini", call.get("name"))
                    c = _dict(call.get("args")).get("command")
                    cmd = c if cls == "shell" and isinstance(c, str) else None
                    yield {"kind": "tool_call", "id": cid, "name": label, "cls": cls,
                           "command": cmd, "ts": ts}
                if status in GEMINI_STATUS and cid not in resolved:
                    resolved.add(cid)
                    yield {"kind": "tool_result", "id": cid,
                           "success": GEMINI_STATUS[status],
                           "text": _text(call.get("resultDisplay")), "ts": ts}
    for inp, out in usage.values():
        yield {"kind": "usage", "ts": None, "input": inp, "output": out}


ADAPTERS = {"claude-code": _claude_events, "codex": _codex_events,
            "grok": _grok_events, "gemini": _gemini_events}


def iter_events(path, harness=None):
    harness = harness or detect_harness(path)
    if harness not in ADAPTERS:
        raise ValueError(f"unrecognized session format: {path}")
    return ADAPTERS[harness](path)


def session_mtime(path):
    """Newest write among the files that make up a session record."""
    p = Path(path)
    if p.is_dir():
        times = [(p / n).stat().st_mtime
                 for n in ("events.jsonl", "updates.jsonl")
                 if (p / n).exists()]
        if times:
            return max(times)
        summary = p / "summary.json"
        return summary.stat().st_mtime if summary.exists() else 0
    if p.exists():
        return p.stat().st_mtime
    return 0


def _codex_meta(path, limit=30):
    """First session_meta payload, or {} if the file has none in the first records."""
    n = 0
    for rec in _iter_jsonl(path):
        n += 1
        if _str(rec.get("type")) == "session_meta":
            return _dict(rec.get("payload"))
        if n >= limit:
            break
    return {}


def is_codex_subagent(path):
    """True when session_meta.source is a subagent spawn (or parent_thread_id is set)."""
    meta = _codex_meta(path)
    src = meta.get("source")
    if isinstance(src, dict) and "subagent" in src:
        return True
    if meta.get("parent_thread_id"):
        return True
    return False


def session_bytes(path):
    p = Path(path)
    if p.is_dir():
        total = 0
        for name in ("events.jsonl", "updates.jsonl"):
            f = p / name
            if f.exists():
                total += f.stat().st_size
        return total
    return p.stat().st_size if p.exists() else 0


def list_sessions(home=None, claude_projects=None):
    """Primary local session records. Dirs for Grok, files otherwise.

    Skips Grok `subagents/` dirs and Codex rollouts whose session_meta marks
    them as subagent threads. Respects $CLAUDE_CONFIG_DIR, $GROK_HOME, $CODEX_HOME
    when the corresponding override is unset.
    """
    default_home = Path.home()
    home = Path(home or default_home)
    use_env = home.resolve() == default_home.resolve()
    found = []
    if claude_projects:
        claude = Path(claude_projects)
    else:
        cfg = os.environ.get("CLAUDE_CONFIG_DIR") if use_env else None
        claude = (Path(cfg).expanduser() / "projects") if cfg else home / ".claude" / "projects"
    if claude.is_dir():
        found.extend(claude.glob("*/*.jsonl"))
    grok_home = os.environ.get("GROK_HOME") if use_env else None
    grok = (Path(grok_home).expanduser() / "sessions") if grok_home else home / ".grok" / "sessions"
    if grok.is_dir():
        for summary in grok.rglob("summary.json"):
            d = summary.parent
            if "subagents" in d.parts:
                continue
            if (d / "events.jsonl").exists() or (d / "updates.jsonl").exists():
                found.append(d)
    codex_home = os.environ.get("CODEX_HOME") if use_env else None
    codex = (Path(codex_home).expanduser() / "sessions") if codex_home else home / ".codex" / "sessions"
    if codex.is_dir():
        for p in codex.glob("*/*/*/rollout-*.jsonl"):
            try:
                if is_codex_subagent(p):
                    continue
            except OSError:
                continue
            found.append(p)
    gemini = home / ".gemini" / "tmp"
    if gemini.is_dir():
        found.extend(gemini.glob("*/chats/session-*.jsonl"))
    return found
