#!/usr/bin/env python3
"""Terminally Cooked — grade one AI-coding session into a comedy results card.

Local-only, zero-upload. Reads a session record already on disk (Claude Code,
Codex, Grok, or Gemini CLI — auto-detected), computes raw observable counts,
attaches comedy buffs/debuffs, and renders an ANSI terminal card in the
red/green diff-counter aesthetic.

Card fields are ALLOWLISTED: no cwd, repo names, branch names, file paths,
prompt text, or tool output ever reaches the card. Product docs: INDEX.md.
"""

import argparse
import base64
import hashlib
import html as html_mod
import json
import os
import re
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import harness_adapters
from harness_adapters import (
    TOOL_CLASSES, detect_harness, iter_events, session_identity, session_label,
    list_sessions, session_mtime, session_bytes,
)

SCORING_VERSION = "scoring-v0.6 (entertainment only)"
CHAIN_PRODUCT_CAP = 6.0     # stacked chain multipliers cap ("within reason")
STREAK_EXP = 1.5            # serialized-event chain superlinearity
STREAK_CAP = 100
WINDOW_SECS = 1200          # 20-min windows for the sustained-skill meta-chain
WINDOW_MIN_EVENTS = 5
WINDOW_CHAIN_EXP = 1.5
WINDOW_CHAIN_UNIT = 150
WINDOW_CHAIN_CAP = 12
PROJECTS_DIR = Path.home() / ".claude" / "projects"
MAX_PICK_BYTES = 50 * 1024 * 1024   # skip monster rollouts when auto-picking
PICK_LOOKBACK_DAYS = 7              # if today has only the live session
PICK_ANALYZE_CAP = 20               # pre-filter by size; do not parse every rollout

# Known-format tally parsing (non-semantic; fails open on no-match).
PASSED_RE = re.compile(r"(\d+)\s+passed\b", re.IGNORECASE)
FAILED_RE = re.compile(r"(\d+)\s+fail(?:ed|ures?)\b", re.IGNORECASE)
CARGO_RESULT = "test result:"
OVERLOAD_RE = re.compile(r"overloaded|\b529\b", re.IGNORECASE)
INTERRUPT_MARKER = "[Request interrupted"


def parse_tally(text):
    """(passed, failed) from one recognized summary line, or None.

    Counts are read independently, in either order, with comma, semicolon or
    pipe separators. The last summary-bearing line wins (pytest, jest and
    vitest end with the suite total); cargo prints one `test result:` line per
    test binary, so those lines are summed."""
    if not isinstance(text, str) or not text:
        return None
    last, cargo = None, [0, 0, 0]
    for line in text.splitlines():
        p, f = PASSED_RE.search(line), FAILED_RE.search(line)
        if not (p or f):
            continue
        tally = (int(p.group(1)) if p else 0, int(f.group(1)) if f else 0)
        if line.strip().lower().startswith(CARGO_RESULT):
            cargo = [cargo[0] + tally[0], cargo[1] + tally[1], cargo[2] + 1]
        last = tally
    if cargo[2]:
        return cargo[0], cargo[1]
    return last


# Tallies only count when the producing command is a recognized test-runner
# invocation; reads, echoes and quoted tallies (docs, cards, logs) never do.
SHELLS = {"bash", "sh", "zsh", "dash", "fish"}
PLAIN_WRAPPERS = {"time", "nice", "command", "exec", "env", "npx", "bunx", "pnpx", "nohup"}
RUN_WRAPPERS = {("uv", "run"), ("poetry", "run"), ("pipenv", "run"), ("bundle", "exec"),
                ("pnpm", "exec"), ("yarn", "dlx"), ("hatch", "run"), ("pdm", "run")}
RUNNER_HEADS = {"pytest", "py.test", "jest", "vitest", "phpunit", "rspec", "ctest",
                "tox", "nox", "cypress"}
SUBCOMMAND_RUNNERS = {"go", "cargo", "mvn", "gradle", "gradlew", "deno", "dotnet",
                      "swift", "mix", "playwright"}
PKG_RUNNERS = {"npm", "yarn", "pnpm", "bun"}
TEST_SCRIPT_RE = re.compile(r"^(?:test_.*|.*_tests?(?:\.\w+)?|run_suite.*|run_tests?(?:\.\w+)?)$")
PYTHON_RE = re.compile(r"^python(?:\d+(?:\.\d+)?)?$")
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _command_segments(cmd):
    try:
        lex = shlex.shlex(cmd.replace("\n", " ; "), posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        return []
    segs, seg = [], []
    for tok in tokens:
        if tok and all(ch in "();&|<>" for ch in tok):
            if seg:
                segs.append(seg)
            seg = []
        else:
            seg.append(tok)
    if seg:
        segs.append(seg)
    return segs


def _strip_wrappers(toks):
    while toks:
        head = os.path.basename(toks[0])
        if ASSIGN_RE.match(toks[0]) or head in PLAIN_WRAPPERS:
            toks = toks[1:]
        elif head == "timeout":
            toks = toks[1:]
            while toks and (toks[0].startswith("-") or toks[0][:1].isdigit()):
                toks = toks[1:]
        elif len(toks) > 1 and (head, toks[1]) in RUN_WRAPPERS:
            toks = toks[2:]
        elif toks[0].startswith("-") and len(toks[0]) > 1:
            toks = toks[1:]          # wrapper flags such as `npx -y`
        else:
            return toks
    return toks


def _is_runner(toks):
    head = os.path.basename(toks[0])
    rest = toks[1:]
    if head in RUNNER_HEADS or TEST_SCRIPT_RE.match(head):
        return True
    if PYTHON_RE.match(head):
        args = [t for t in rest if t != "-u"]
        if len(args) >= 2 and args[0] == "-m" and args[1] in ("pytest", "unittest"):
            return True
        script = next((t for t in args if not t.startswith("-")), None)
        return bool(script and TEST_SCRIPT_RE.match(os.path.basename(script)))
    if not rest:
        return False
    if head in SUBCOMMAND_RUNNERS:
        return rest[0] in ("test", "nextest")
    if head == "make":
        return rest[0].startswith("test") or rest[0] == "check"
    if head in PKG_RUNNERS:
        if rest[0] in ("test", "t"):
            return True
        return len(rest) > 1 and rest[0] == "run" and rest[1].startswith(("test", "e2e"))
    return False


def is_test_command(cmd, depth=0):
    """True when some segment of a shell command invokes a known test runner."""
    if not isinstance(cmd, str):
        return False
    for seg in _command_segments(cmd):
        toks = _strip_wrappers(seg)
        if not toks:
            continue
        if os.path.basename(toks[0]) in SHELLS:
            if depth < 2:
                for i, tok in enumerate(toks[1:-1], 1):
                    if tok.startswith("-") and "c" in tok:
                        if is_test_command(toks[i + 1], depth + 1):
                            return True
                        break
            continue
        if _is_runner(toks):
            return True
    return False


_FRACTION_RE = re.compile(r"(\d{2}:\d{2}:\d{2})[.,](\d+)")
_COMPACT_OFFSET_RE = re.compile(r"(T.*[+-]\d{2})(\d{2})$")


def parse_ts(ts):
    """Aware datetime from an ISO-8601 transcript timestamp, or None.

    Python 3.9's fromisoformat accepts neither `Z` nor fraction lengths other
    than 3 or 6 digits, and harnesses emit both. Naive stamps are read as UTC
    so they can be compared with aware ones."""
    if not isinstance(ts, str) or not ts.strip():
        return None
    t = ts.strip()
    if t[-1:] in ("Z", "z"):
        t = t[:-1] + "+00:00"
    t = _FRACTION_RE.sub(lambda m: m.group(1) + "." + (m.group(2) + "000000")[:6], t, count=1)
    t = _COMPACT_OFFSET_RE.sub(r"\1:\2", t)
    try:
        d = datetime.fromisoformat(t)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def zone_label(tz):
    key = getattr(tz, "key", None)
    if isinstance(key, str):
        return key
    off = tz.utcoffset(None) or timedelta(0)
    mins = int(off.total_seconds() // 60)
    sign = "+" if mins >= 0 else "-"
    return f"UTC{sign}{abs(mins) // 60:02d}:{abs(mins) % 60:02d}"


def parse_zone(text):
    """tzinfo from `UTC`, a `±HH:MM` / `±HHMM` offset, or an IANA zone name."""
    t = str(text).strip()
    if t.upper() in ("UTC", "Z", "GMT"):
        return timezone.utc
    m = re.fullmatch(r"(?:UTC)?([+-])(\d{1,2}):?(\d{2})?", t, re.IGNORECASE)
    if m:
        hours, mins = int(m.group(2)), int(m.group(3) or 0)
        if hours > 23 or mins > 59:
            raise ValueError(f"bad UTC offset: {t}")
        off = timedelta(hours=hours, minutes=mins)
        return timezone(-off if m.group(1) == "-" else off)
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(t)
    except Exception as exc:
        raise ValueError(f"unknown time zone: {t}") from exc


def iter_records(path):
    with open(path) as f:
        for line in f:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def tool_result_text(block):
    inner = block.get("content")
    if isinstance(inner, str):
        return inner
    if isinstance(inner, list):
        return " ".join(x.get("text", "") for x in inner if isinstance(x, dict))
    return ""


def _hash_name(root, hash_path):
    root, hash_path = Path(root), Path(hash_path)
    if root.is_dir():
        try:
            return str(hash_path.relative_to(root))
        except ValueError:
            pass
    return hash_path.name


def analyze(path, harness=None, tz=None):
    """Grade one session from any supported harness. Detection is automatic;
    parsing is delegated to harness_adapters, bookkeeping happens here.

    tz fixes the zone Night Shift reads hours in. Default: the local UTC
    offset at the session's first timestamp, recorded in the stamp so a
    recompute elsewhere can pass it back with --tz."""
    harness = harness or detect_harness(path) or "claude-code"
    label, hash_paths = session_identity(path, harness)
    sha = hashlib.sha256()
    for hash_path in hash_paths:
        hp = Path(hash_path)
        name = _hash_name(path, hp).encode()
        sha.update(len(name).to_bytes(4, "big"))
        sha.update(name)
        if hp.is_dir():                         # a checkpoint entry: presence only
            sha.update((0).to_bytes(8, "big"))
            continue
        sha.update(hp.stat().st_size.to_bytes(8, "big"))
        with open(hp, "rb") as fh:              # chunked: transcripts can be huge
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                sha.update(chunk)
    digest = sha.hexdigest()
    s = {
        "session_id": label[:8] if label else digest[:8],
        "harness": harness,
        "transcript_sha": digest,
        "tz": zone_label(tz) if tz else None,
        "models": {},
        "efforts": {},
        "tools": {},
        "tool_classes": {},
        "green": 0,
        "red": 0,
        "unknown_results": 0,   # tri-state: results with no derivable success flag
        "longest_streak": 0,
        "worst_spiral": 0,
        "interruptions": 0,
        "compactions": 0,
        "first_tally": None,
        "last_tally": None,
        "first_ts": None,
        "last_ts": None,
        "user_prompts": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "yolo_mode": False,
        "plan_entries": 0,
        "overloads": 0,
        "longest_cook": 0,
        "night_events": 0,
        "worst_doom_loop": 0,
        "clean_window_chain": 0,
        "charm": False,        # a run of exactly 3 errors was followed by a success
    }
    streak = spiral = cook = 0
    windows = {}       # window index -> [events, errors]
    tallies = {}       # normalized test command -> [first_tally, last_tally, samples]
    pending = {}       # tool call id -> command string (never rendered)
    last_failed_cmd, doom_run = None, 0
    t0 = t_max = None
    for ev in iter_events(path, harness):
        ts = ev.get("ts")
        when = parse_ts(ts)
        if isinstance(ts, str) and ts:
            if s["first_ts"] is None:
                s["first_ts"] = ts
                t0 = when
            s["last_ts"] = ts
        if when is not None:
            if tz is None:
                tz = timezone(when.astimezone().utcoffset() or timedelta(0))
                s["tz"] = zone_label(tz)
            if 2 <= when.astimezone(tz).hour < 6:
                s["night_events"] += 1
            if t0 is not None and when >= t0 and (t_max is None or when > t_max):
                t_max = when
        kind = ev.get("kind")
        if kind == "compaction":
            s["compactions"] += 1
        elif kind == "permission":
            if ev.get("mode") == "bypass":
                s["yolo_mode"] = True
            elif ev.get("mode") == "plan":
                s["plan_entries"] += 1
        elif kind == "model":
            if isinstance(ev.get("model"), str) and ev["model"]:
                s["models"][ev["model"]] = s["models"].get(ev["model"], 0) + 1
            if isinstance(ev.get("effort"), str) and ev["effort"]:
                s["efforts"][ev["effort"]] = s["efforts"].get(ev["effort"], 0) + 1
        elif kind == "usage":
            s["tokens_in"] += int(ev.get("input") or 0)
            s["tokens_out"] += int(ev.get("output") or 0)
        elif kind == "human":
            s["user_prompts"] += 1
            cook = 0
        elif kind == "interrupt":
            s["interruptions"] += 1
        elif kind == "tool_call":
            name = safe_meta(ev.get("name") or "Other") or "Other"
            s["tools"][name] = s["tools"].get(name, 0) + 1
            cls = ev.get("cls") if ev.get("cls") in TOOL_CLASSES else "other"
            s["tool_classes"][cls] = s["tool_classes"].get(cls, 0) + 1
            if isinstance(ev.get("command"), str):
                pending[ev.get("id")] = ev["command"].strip()
        elif kind == "tool_result":
            success = ev.get("success")
            if when is not None and t0 is not None and success is not None:
                # unknown outcomes must not populate "clean" windows either —
                # they touch neither positive nor negative chains, anywhere
                wi = int((when - t0).total_seconds() // WINDOW_SECS)
                if wi >= 0:  # out-of-order timestamps never land in a bucket
                    w = windows.setdefault(wi, [0, 0])
                    w[0] += 1
                    if success is False:
                        w[1] += 1
            cmd = pending.pop(ev.get("id"), None)
            text = ev.get("text") if isinstance(ev.get("text"), str) else ""
            if success is None:
                # tri-state: unknown outcomes touch neither streaks nor spirals
                s["unknown_results"] += 1
            elif success is False:
                s["red"] += 1
                cook = 0  # an error breaks the unsupervised-success chain
                if OVERLOAD_RE.search(text):
                    s["overloads"] += 1
                if cmd is not None:
                    doom_run = doom_run + 1 if cmd == last_failed_cmd else 1
                    last_failed_cmd = cmd
                    s["worst_doom_loop"] = max(s["worst_doom_loop"], doom_run)
                spiral += 1
                s["worst_spiral"] = max(s["worst_spiral"], spiral)
                streak = 0
            else:
                s["green"] += 1
                cook += 1  # unsupervised-success chain grows on green results only
                s["longest_cook"] = max(s["longest_cook"], cook)
                if cmd is not None:
                    last_failed_cmd, doom_run = None, 0
                streak += 1
                s["longest_streak"] = max(s["longest_streak"], streak)
                if spiral == 3:
                    s["charm"] = True   # exactly three errors, then this success
                spiral = 0
            if success is not None and cmd is not None and is_test_command(cmd):
                tally = parse_tally(text)
                if tally:
                    # per-command tracking: deltas only compare like with like,
                    # so a full-suite run followed by one focused test can't
                    # register as a fictional regression
                    entry = tallies.setdefault(" ".join(cmd.split()), [tally, tally, 0])
                    entry[1] = tally
                    entry[2] += 1
    if s["tz"] is None:
        s["tz"] = zone_label(tz or timezone.utc)
    # the tally pair comes from the most-sampled test command; ties go to the
    # larger suite, so first/last always describe the same, biggest run
    picked = max(tallies.values(),
                 key=lambda e: (e[2], max(sum(e[0]), sum(e[1]))), default=None)
    if picked and picked[2] >= 2:
        s["first_tally"], s["last_tally"] = picked[0], picked[1]
    elif picked:
        s["first_tally"] = s["last_tally"] = picked[1]   # single run: shown, no delta
    # only COMPLETED windows qualify: every bucket before the one holding the
    # session's latest timestamp has elapsed; that final bucket never counts,
    # so "three 20-minute windows" cannot be earned in twenty-one minutes
    final_bucket = int((t_max - t0).total_seconds() // WINDOW_SECS) if t_max else 0
    run = best = sparse = 0
    for i in range(final_bucket):
        ev, er = windows.get(i, (0, 0))
        if ev >= WINDOW_MIN_EVENTS and er == 0:
            run += 1
            sparse = 0
            best = max(best, run)
        elif er > 0:
            run = sparse = 0
        else:
            # sparse window: one holds the chain (thinking is allowed);
            # two consecutive reset it (walking away is not a chain)
            sparse += 1
            if sparse >= 2:
                run = sparse = 0
    s["clean_window_chain"] = best
    return s


# Badge glyphs: terminal-native monochrome codepoints, never emoji — the card
# is a diff, not a Duolingo streak. Paired arrows are deliberate: ↻ Doom Loop
# (repeating the same thing), ↺ Error Spiral (spinning backwards).
ICONS = {
    "ONE-SHOT WONDER": "◎", "FLOW STATE": "≋", "Clean Streak": "⇉",
    "LET IT COOK": "♨", "THE LONG GAME": "♟",
    "Red Wedding": "☠", "Error Spiral": "↺", "Doom Loop": "↻",
    "Backseat Driver": "‼", "All Plan No Game": "☰", "Twenty Questions": "¿",
    "Third Time's the Charm": "☘", "Overloaded": "⏻",
    "YOLO MODE": "»", "Token Bonfire": "🜂", "Night Shift": "☾",
    "Marathon": "∞", "Test Whisperer": "✓", "Speedrun": "↯",
    "Middle Manager": "⑂", "Lost the Tapes": "⌫", "Model Hopper": "⇄",
    "Bookworm": "¶", "Perfectly Balanced": "≍",
}

# Badge art: winning render per modifier, chosen by blind vote (see
# docs/art/voting-protocol.md). Embedded as data URIs so a shared card stays
# self-contained; the terminal card keeps the glyphs above.
BADGE_DIR = Path(__file__).parent / "assets" / "badges"
LOGO_PATH = Path(__file__).parent / "assets" / "logo.png"
SLUGS = {
    "ONE-SHOT WONDER": "one_shot_wonder", "FLOW STATE": "flow_state",
    "Clean Streak": "clean_streak", "LET IT COOK": "let_it_cook",
    "THE LONG GAME": "long_game", "Red Wedding": "red_wedding",
    "Error Spiral": "error_spiral", "Doom Loop": "doom_loop",
    "Backseat Driver": "backseat_driver", "All Plan No Game": "all_plan_no_game",
    "Twenty Questions": "twenty_questions", "Third Time's the Charm": "third_times_charm",
    "Overloaded": "overloaded", "YOLO MODE": "yolo_mode",
    "Token Bonfire": "token_bonfire", "Night Shift": "night_shift",
    "Marathon": "marathon", "Test Whisperer": "test_whisperer",
    "Speedrun": "speedrun", "Middle Manager": "middle_manager",
    "Lost the Tapes": "lost_the_tapes", "Model Hopper": "model_hopper",
    "Bookworm": "bookworm", "Perfectly Balanced": "perfectly_balanced",
}


def badge_data_uri(name, size=72):
    """Return the badge art as a data URI, or None when the asset is absent."""
    slug = SLUGS.get(name)
    if not slug:
        return None
    path = BADGE_DIR / f"{slug}_{size}.png"
    if not path.exists():
        return None
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def logo_data_uri():
    """Full-bleed gothic wordmark, or None when the asset is absent."""
    if not LOGO_PATH.exists():
        return None
    return "data:image/png;base64," + base64.b64encode(LOGO_PATH.read_bytes()).decode()


SAFE_META_RE = re.compile(r"[^A-Za-z0-9._+\- ]")
CONTROL_RE = re.compile("[\x00-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
HARNESSES = ("claude-code", "codex", "grok", "gemini")


def safe_meta(value, limit=40):
    """Model/effort names come from the transcript and are untrusted for
    rendering: strip to a conservative charset before ANSI or HTML output."""
    return SAFE_META_RE.sub("", str(value))[:limit]


def clean(value):
    """Drop terminal controls and bidi overrides from any rendered string."""
    return CONTROL_RE.sub("", str(value))


def meta_names(d):
    return ", ".join(safe_meta(k) for k in sorted(d, key=d.get, reverse=True))


def card_fields(s):
    """The only dynamic values a card, caption, or output filename may show,
    each re-validated here whatever produced the stats dict."""
    sid = re.sub(r"[^0-9a-f]", "", str(s.get("session_id", "")).lower())[:8] or "unknown"
    date = str(s.get("first_ts") or "")[:10]
    tools = sorted(((safe_meta(k, 24) or "Other", int(v)) for k, v in s.get("tools", {}).items()),
                   key=lambda kv: -kv[1])[:6]
    return {
        "sid": sid,
        "date": date if DATE_RE.fullmatch(date) else "?",
        "models": meta_names(s.get("models", {})),
        "efforts": meta_names(s.get("efforts", {})),
        "tools": "  ".join(f"{k}:{v}" for k, v in tools),
        "harness": s.get("harness") if s.get("harness") in HARNESSES else "unknown",
        "tz": re.sub(r"[^A-Za-z0-9_+\-/:]", "", str(s.get("tz") or "?"))[:40],
    }


def duration_minutes(s):
    t0, t1 = parse_ts(s.get("first_ts")), parse_ts(s.get("last_ts"))
    if t0 is None or t1 is None:
        return None
    return max(1, int((t1 - t0).total_seconds() // 60))


def division(s):
    """Session length class, like a chess time control. Labels only — divisions
    never normalize the score, they tell the reader which game was played."""
    mins = duration_minutes(s)
    if mins is None:
        return "?"
    if mins < 15:
        return "blitz"
    if mins < 120:
        return "sprint"
    return "long haul"


def delegation_note(s):
    n = s.get("tool_classes", {}).get("agent", 0)
    return f"delegation: {n} subagent call(s) · internals not graded" if n else None


def pick_buffs(s):
    """The modifier catalog. Three kinds:
    - "chain": multiplies — earned only by serialized sustained success
    - "debuff": multiplies down — errors are always real
    - "flavor": flat point bonus — context/comedy, never compounds
    Values are jokes, not measurement."""
    buffs = []  # (name, kind, value, line)
    total = s["green"] + s["red"]
    cls = s.get("tool_classes", {})    # canonical classes, so every harness can earn these
    mins = duration_minutes(s)

    # chains (serialized skill -> multiplies)
    # streak-derived chains are one correlated group: only the strongest applies
    if s["red"] == 0 and total >= 20:
        buffs.append(("ONE-SHOT WONDER", "chain", 1.6, "an entire session, zero errors. suspicious."))
    elif s["longest_streak"] >= 25:
        buffs.append(("FLOW STATE", "chain", 1.5, f"{s['longest_streak']} green results without a miss"))
    elif s["longest_streak"] >= 10:
        buffs.append(("Clean Streak", "chain", 1.2, f"{s['longest_streak']} in a row"))
    ft, lt = s["first_tally"], s["last_tally"]
    if s["longest_cook"] >= 50:
        buffs.append(("LET IT COOK", "chain", 1.3, f"{s['longest_cook']} straight green calls, zero supervision"))
    if s["clean_window_chain"] >= 3:
        buffs.append(("THE LONG GAME", "chain", 1.0 + 0.1 * min(s["clean_window_chain"], WINDOW_CHAIN_CAP),
                      f"{s['clean_window_chain']} consecutive clean 20-min windows"))

    # debuffs (multiply down)
    if s["worst_spiral"] >= 4:
        buffs.append(("Error Spiral", "debuff", 0.7, f"{s['worst_spiral']} consecutive faceplants"))
    elif s["worst_spiral"] == 3 and s["charm"]:
        buffs.append(("Third Time's the Charm", "debuff", 0.9, "3 straight errors, then grace"))
    if ft and lt and lt[1] > ft[1]:
        buffs.append(("Red Wedding", "debuff", 0.6, f"failures went {ft[1]} -> {lt[1]}"))
    if cls.get("ask", 0) >= 4:
        buffs.append(("Twenty Questions", "debuff", 0.9, f"asked the human {cls['ask']} times"))
    if s["interruptions"] >= 3:
        buffs.append(("Backseat Driver", "debuff", 0.8, f"human slammed the brakes {s['interruptions']} times"))
    if s["plan_entries"] >= 1 and cls.get("edit", 0) == 0:
        buffs.append(("All Plan No Game", "debuff", 0.8, f"entered plan mode {s['plan_entries']}x, zero edit/write calls"))
    if s["overloads"] >= 1:
        buffs.append(("Overloaded", "debuff", 0.9, f"the API said no, {s['overloads']}x (rare)"))
    if s["worst_doom_loop"] >= 3:
        buffs.append(("Doom Loop", "debuff", 0.7, f"same command failed {s['worst_doom_loop']}x"))

    # flavor (flat bonus, never compounds)
    if ft and lt and lt[0] > ft[0]:
        buffs.append(("Test Whisperer", "flavor", 150, f"{ft[0]} passed -> {lt[0]} passed"))
    if s["yolo_mode"]:
        buffs.append(("YOLO MODE", "flavor", 250, "--dangerously-skip-permissions. respect."))
    if s["tokens_in"] >= 100_000_000 or s["tokens_out"] >= 1_000_000:
        buffs.append(("Token Bonfire", "flavor", 200, f"{s['tokens_in']/1e6:.0f}M tokens. the meter is spinning."))
    if s["night_events"] >= 10:
        buffs.append(("Night Shift", "flavor", 200, "real work happening between 2 and 6 am"))
    if mins and mins >= 240:
        buffs.append(("Marathon", "flavor", 200, f"{mins // 60}h {mins % 60}m in the chair"))
    elif mins and mins <= 10 and total >= 10:
        buffs.append(("Speedrun", "flavor", 150, f"in and out in {mins} minutes"))
    if cls.get("agent", 0) >= 5:
        buffs.append(("Middle Manager", "flavor", 150, f"delegated to {cls['agent']} subagents"))
    if s["compactions"] >= 1:
        buffs.append(("Lost the Tapes", "flavor", 100, f"survived {s['compactions']} compaction(s); records incomplete"))
    if len(s["models"]) >= 3:
        buffs.append(("Model Hopper", "flavor", 100, f"{len(s['models'])} different models in one session"))
    reads, bashes = cls.get("read", 0), cls.get("shell", 0)
    if reads >= 20 and reads > bashes:
        buffs.append(("Bookworm", "flavor", 50, f"read {reads} files, touched grass never"))
    if not buffs:
        buffs.append(("Perfectly Balanced", "flavor", 0, "as all things should be"))
    return buffs


def score_parts(s, buffs):
    """Chains multiply (capped); serialized success scores superlinearly;
    flavor adds flat on top of the floored core; debuffs bite the core."""
    base = s["green"] * 10 - s["red"] * 15
    base += int(min(s["longest_streak"], STREAK_CAP) ** STREAK_EXP)
    base += int(WINDOW_CHAIN_UNIT * min(s["clean_window_chain"], WINDOW_CHAIN_CAP) ** WINDOW_CHAIN_EXP)
    ft, lt = s["first_tally"], s["last_tally"]
    if ft and lt:
        base += (lt[0] - ft[0]) * 25
    chain = 1.0
    debuff = 1.0
    flat = 0
    for _, kind, value, _ in buffs:
        if kind == "chain":
            chain *= value
        elif kind == "debuff":
            debuff *= value
        else:
            flat += value
    chain = min(chain, CHAIN_PRODUCT_CAP)
    return max(0, int(base * chain * debuff)), flat


def score(s, buffs):
    core, flat = score_parts(s, buffs)
    return core + flat


class C:
    on = sys.stdout.isatty() or os.environ.get("FORCE_COLOR")
    @classmethod
    def c(cls, code, text):
        return f"\033[{code}m{text}\033[0m" if cls.on else text
    @classmethod
    def green(cls, t): return cls.c("32", t)
    @classmethod
    def red(cls, t): return cls.c("31", t)
    @classmethod
    def dim(cls, t): return cls.c("2", t)
    @classmethod
    def bold(cls, t): return cls.c("1", t)
    @classmethod
    def yellow(cls, t): return cls.c("33", t)


def fever_bar(s, width=30):
    total = s["green"] + s["red"]
    if not total:
        return C.dim("░" * width)
    fill = round(width * s["green"] / total)
    return C.green("█" * fill) + C.red("░" * (width - fill))


def render(s, buffs, final):
    f = card_fields(s)
    mins = duration_minutes(s)
    dur = f"{mins // 60}h {mins % 60}m" if mins else "unknown"
    w = 62
    line = "─" * w
    out = []
    out.append(C.dim("┌" + line + "┐"))
    out.append(C.bold("  TERMINALLY COOKED") + C.dim(f"  ·  session {f['sid']}  ·  {f['date']}  ·  {dur}  ·  {division(s)}"))
    out.append(C.dim(f"  {f['models']}  ·  effort: {f['efforts']}"))
    dn = delegation_note(s)
    if dn:
        out.append(C.dim(f"  {dn}"))
    out.append(C.dim("├" + line + "┤"))
    out.append("  " + fever_bar(s) + C.dim("  fever"))
    unknown = f"   ?{s['unknown_results']} unknown" if s.get("unknown_results") else ""
    out.append(C.green(f"  +{s['green']} tool results") + "   " + C.red(f"-{s['red']} errors")
               + "   " + C.yellow(f"streak {s['longest_streak']}") + C.dim(unknown))
    ft, lt = s["first_tally"], s["last_tally"]
    if ft and lt:
        out.append(C.red(f"  - # {ft[0]} tests passed, {ft[1]} failed"))
        out.append(C.green(f"  + # {lt[0]} tests passed, {lt[1]} failed"))
    out.append(C.dim(f"  {f['tools']}"))
    if s["tokens_in"] or s["tokens_out"]:
        out.append(C.dim(f"  tokens: {s['tokens_in']/1e6:,.1f}M in · {s['tokens_out']/1e6:,.2f}M out"))
    out.append(C.dim("├" + line + "┤"))
    for name, kind, value, why in buffs:
        name, why = clean(name), clean(why)
        glyph = ICONS.get(name, "·")
        if kind == "flavor":
            tag = C.dim(f"+{value}")
        elif value >= 1:
            tag = C.green(f"×{round(value, 2)}")
        else:
            tag = C.red(f"×{value}")
        out.append(f"  {C.yellow(glyph) if kind == 'chain' else C.dim(glyph)} {C.bold(name):<38} {tag}  {C.dim(why)}")
    out.append(C.dim("├" + line + "┤"))
    core, flat = score_parts(s, buffs)
    out.append(C.bold(f"  FINAL: {C.yellow(f'+{final:,}')}")
               + C.dim(f"  (skill {core:,} · comedy {flat:,} · means nothing. share it anyway.)"))
    out.append(C.dim(f"  {SCORING_VERSION} · adapter {f['harness']} · {fingerprint(s)}"))
    out.append(C.dim("└" + line + "┘"))
    return "\n".join(out)


CODE_FILES = (Path(__file__).resolve(), Path(harness_adapters.__file__).resolve())


def code_hash():
    """Both modules decide the score: the adapters normalize, this file grades."""
    h = hashlib.sha256()
    for f in CODE_FILES:
        body = f.read_bytes()
        name = f.name.encode()
        h.update(len(name).to_bytes(4, "big") + name + len(body).to_bytes(8, "big"))
        h.update(body)
    return h.hexdigest()


def fingerprint(s):
    """Verification stamp: recomputing with the official code on the same
    session files, with the stamped time zone (--tz), must reproduce the
    score. Detects edited numbers and modified grading code; does not prove
    the transcript itself is genuine."""
    sha = re.sub(r"[^0-9a-f]", "", str(s.get("transcript_sha", "")))[:12]
    return f"recompute: transcript {sha} · code {code_hash()[:8]} · tz {card_fields(s)['tz']}"


def render_html(s, buffs, final):
    """Standalone shareable card. Same field allowlist as the ANSI card."""
    f = card_fields(s)
    mins = duration_minutes(s)
    dur = f"{mins // 60}h {mins % 60}m" if mins else "unknown"
    total = s["green"] + s["red"]
    pct = round(100 * s["green"] / total) if total else 0
    esc = html_mod.escape

    def chip(name, kind, value, why):
        name, why = clean(name), clean(why)
        glyph = ICONS.get(name, "·")
        tag = (f"+{value}" if kind == "flavor" else f"&times;{round(value, 2)}")
        art = badge_data_uri(name)
        tile = (f'<img class="tile art" src="{art}" alt="">' if art
                else f'<span class="tile">{esc(glyph)}</span>')
        return (f'<div class="badge {esc(kind)}">{tile}'
                f'<span class="bmeta"><span class="brow"><span class="bname">{esc(name)}</span>'
                f'<span class="btag">{tag}</span></span>'
                f'<span class="bwhy">{esc(why)}</span></span></div>')
    rows = ('<div class="badges">'
            + "".join(chip(*b) for b in buffs)
            + '</div>')
    tally = ""
    if s["first_tally"] and s["last_tally"]:
        ft, lt = s["first_tally"], s["last_tally"]
        tally = (f'<div class="diff"><div class="rm">- {ft[0]} tests passed, {ft[1]} failed</div>'
                 f'<div class="add">+ {lt[0]} tests passed, {lt[1]} failed</div></div>')
    tokens = ""
    if s["tokens_in"] or s["tokens_out"]:
        tokens = (f'<div class="meta tokens">tokens: {s["tokens_in"]/1e6:,.1f}M in'
                  f' &middot; {s["tokens_out"]/1e6:,.2f}M out</div>')
    core, flat = score_parts(s, buffs)
    note = delegation_note(s)
    unknown = (f' &middot; <span class="lbl">?{int(s["unknown_results"])} unknown</span>'
               if s.get("unknown_results") else "")
    logo = logo_data_uri()
    header = (f'<img class="wordmark" src="{logo}" alt="TERMINALLY COOKED">'
              if logo else "<h1>TERMINALLY COOKED</h1>")
    return f"""<!-- terminally-cooked shareable card -->
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{CARD_CSP}">
<div style="max-width:560px">
<style>
.lg-card{{font-family:'SF Mono',Menlo,monospace;background:#ffcc00;color:#111;border:3px solid #111;border-radius:10px;padding:18px 22px 20px;font-size:15px;line-height:1.45;overflow:hidden}}
.lg-card .wordmark{{display:block;width:calc(100% + 44px);margin:-18px -22px 12px;height:auto}}
.lg-card h1{{font-size:28px;margin:0 0 6px;letter-spacing:.04em;color:#111;font-weight:800;line-height:1.05}}
.lg-card .hero{{margin:0 0 22px}}
.lg-card .final{{margin:0 0 4px;padding:0;border:0;font-size:52px;line-height:1;color:#111;background:transparent;font-weight:800;letter-spacing:-.04em}}
.lg-card .tagline{{color:#111;font-size:14px;margin:0 0 4px;font-weight:700}}
.lg-card .joke{{color:#1a1a1a;font-size:14px;margin:0;font-weight:400;font-style:italic}}
.lg-card .evidence{{margin:0 0 22px}}
.lg-card .meta{{color:#333;font-size:13px;line-height:1.4}}
.lg-card .meta.quiet{{color:#666;font-size:12px;font-weight:500;margin:0}}
.lg-card .meta.quiet + .meta.quiet{{margin-top:2px}}
.lg-card .counts{{margin:0 0 4px;font-size:16px;font-weight:800}}
.lg-card .g{{color:#0a7a2f}}.lg-card .r{{color:#8b1500}}.lg-card .y{{color:#111}}
.lg-card .lbl{{color:#333;font-weight:600}}
.lg-card .meter{{margin:0 0 6px}}
.lg-card .fever{{height:12px;border-radius:2px;background:#b91c1c;overflow:hidden;margin:0;border:1px solid #111;box-sizing:border-box}}
.lg-card .meter:has(.diff){{border:1px solid #111;border-radius:2px;overflow:hidden}}
.lg-card .meter:has(.diff) .fever{{border:none;border-radius:0}}
.lg-card .fever i{{display:block;height:100%;width:{pct}%;background:#0a7a2f}}
.lg-card .diff{{margin:0;font-weight:700;font-size:15px;line-height:1.5}}
.lg-card .rm,.lg-card .add{{box-sizing:border-box;width:100%;padding:5px 12px;border-left:4px solid}}
.lg-card .rm{{background:#ffecea;color:#9f1239;border-left-color:#e11d48}}
.lg-card .add{{background:#dcfce7;color:#14532d;border-left-color:#16a34a}}
.lg-card .tokens{{margin:4px 0 0}}
.lg-card .badges{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px;margin:14px 0 10px}}
.lg-card .badge{{display:flex;gap:10px;align-items:center;border:2px solid #111;border-radius:8px;padding:8px 10px;background:#1a1a1a}}
.lg-card .badge .tile{{flex:none;width:52px;height:52px;display:flex;align-items:center;justify-content:center;font-size:20px;border:2px solid #111;border-radius:8px;background:#111;color:#ffcc00}}
.lg-card .badge .tile.art{{object-fit:cover;padding:0}}
.lg-card .badge.chain{{border-color:#111;box-shadow:3px 3px 0 #111}}
.lg-card .badge.chain .tile{{color:#ffcc00;border-color:#111}}
.lg-card .badge.chain .btag{{color:#ffcc00}}
.lg-card .badge.debuff{{border-color:#b91c1c}}
.lg-card .badge.debuff .tile{{color:#ffcc00;border-color:#b91c1c}}
.lg-card .badge.debuff .btag{{color:#ff6b5a}}
.lg-card .badge.flavor .btag{{color:#bbb}}
.lg-card .bmeta{{min-width:0;display:flex;flex-direction:column;gap:2px;flex:1}}
.lg-card .brow{{display:flex;justify-content:space-between;gap:8px;align-items:baseline}}
.lg-card .bname{{font-weight:800;color:#ffcc00;font-size:14px;line-height:1.25}}
.lg-card .btag{{font-weight:800;font-size:14px;flex:none;color:#fff}}
.lg-card .bwhy{{color:#ccc;font-size:13px;line-height:1.35}}
.lg-card .fine{{color:#333;font-size:13px}}
</style>
<div class="lg-card">
{header}
<div class="hero">
<div class="final">+{final:,}</div>
<div class="tagline">skill {core:,} &middot; comedy {flat:,}</div>
<div class="joke">means nothing. share it anyway.</div>
</div>
<div class="evidence">
<div class="counts"><span class="g">+{s['green']}</span> <span class="lbl">tool results</span> &middot; <span class="r">{s['red']}</span> <span class="lbl">errors</span> &middot; <span class="y">streak {s['longest_streak']}</span>{unknown}</div>
<div class="meter">
<div class="fever"><i></i></div>
{tally}</div>
{tokens}
</div>
<div class="meta quiet">session {esc(f['sid'])} &middot; {esc(f['date'])} &middot; {dur} &middot; {division(s)}</div>
<div class="meta quiet">{esc(f['models'])} &middot; effort: {esc(f['efforts'])}</div>
{f'<div class="meta quiet">{esc(note)}</div>' if note else ''}
{f'<div class="meta quiet tools">{esc(f["tools"])}</div>' if f['tools'] else ''}
{rows}
<div class="fine">{SCORING_VERSION} &middot; adapter {esc(f['harness'])} &middot; {esc(fingerprint(s))}</div>
</div></div>
"""


CARD_CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'"
PNG_SIG = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB`\x82"
PNG_CHROMA = (255, 0, 255)          # screenshot key; not used in the card
PNG_FILL = (255, 204, 0)            # #ffcc00 — same as the yellow card; pad is the card, not a frame
PNG_PAD = 24                        # keep rounded corners off the PNG edge; pad matches the card, not a mat


def html_page_for_png(fragment):
    """Full document for rasterizing: magenta key around the card."""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<meta http-equiv='Content-Security-Policy' content=\"{CARD_CSP}\">"
        "<style>html,body{margin:0;padding:24px;background:#ff00ff;}</style>"
        "</head><body>" + fragment + "</body></html>"
    )


def _png_chunk(tag, data):
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def write_png_rgb(path, rows):
    """Write an 8-bit RGB PNG. rows is a list of lists of (r,g,b)."""
    h = len(rows)
    w = len(rows[0]) if h else 0
    raw = b""
    for row in rows:
        raw += b"\x00" + bytes(c for px in row for c in px[:3])
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    data = (
        PNG_SIG
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )
    Path(path).write_bytes(data)


def read_png_rgb(path):
    """Read an 8-bit RGB or RGBA PNG into rows of (r,g,b). A truncated or
    corrupt file raises ValueError, never a codec traceback."""
    try:
        return _read_png_rgb(Path(path).read_bytes())
    except (zlib.error, struct.error, IndexError) as exc:
        raise ValueError(f"truncated or corrupt PNG ({exc})") from exc


def _read_png_rgb(data):
    if data[:8] != PNG_SIG:
        raise ValueError("not a PNG")
    pos = 8
    w = h = bit = color = inter = None
    idat = b""
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if tag == b"IHDR":
            w, h, bit, color, _comp, _flt, inter = struct.unpack(">IIBBBBB", chunk)
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"IEND":
            break
    if None in (w, h, bit, color) or bit != 8 or inter != 0 or color not in (2, 6):
        raise ValueError("unsupported PNG")
    bpp = 3 if color == 2 else 4
    raw = zlib.decompress(idat)
    stride = w * bpp
    rows, i, prev = [], 0, b"\x00" * stride

    def paeth(a, b, c):
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        if pa <= pb and pa <= pc:
            return a
        return b if pb <= pc else c

    for _ in range(h):
        ftype = raw[i]
        scan = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        if ftype == 1:
            for x in range(stride):
                scan[x] = (scan[x] + (scan[x - bpp] if x >= bpp else 0)) & 255
        elif ftype == 2:
            for x in range(stride):
                scan[x] = (scan[x] + prev[x]) & 255
        elif ftype == 3:
            for x in range(stride):
                left = scan[x - bpp] if x >= bpp else 0
                scan[x] = (scan[x] + ((left + prev[x]) // 2)) & 255
        elif ftype == 4:
            for x in range(stride):
                left = scan[x - bpp] if x >= bpp else 0
                up_l = prev[x - bpp] if x >= bpp else 0
                scan[x] = (scan[x] + paeth(left, prev[x], up_l)) & 255
        elif ftype != 0:
            raise ValueError("bad PNG filter")
        prev = bytes(scan)
        if color == 2:
            rows.append([tuple(scan[x:x + 3]) for x in range(0, stride, 3)])
        else:
            rows.append([tuple(scan[x:x + 3]) for x in range(0, stride, 4)])
    return rows


def _is_chroma_px(px, chroma=PNG_CHROMA):
    """True for the screenshot key and the pink anti-alias Chrome leaves on it."""
    r, g, b = px[0], px[1], px[2]
    cr, cg, cb = chroma
    if r == cr and g == cg and b == cb:
        return True
    if abs(r - cr) <= 48 and abs(g - cg) <= 48 and abs(b - cb) <= 48:
        return True
    # anti-aliased magenta against the dark card: R and B both sit above G, R≈B
    return r > g + 40 and b > g + 40 and abs(r - b) <= 50


def crop_png_chroma(src, dest, chroma=PNG_CHROMA, fill=PNG_FILL, pad=PNG_PAD):
    """AABB of the card plus a short pad of card fill. Edge-connected chroma
    (plus anti-aliased pink) becomes that fill so rounded-corner leftovers are
    not a magenta halo. Interior purple (badge art) stays. Do not use a light
    mat — the owner rejected a white/cream frame around the image."""
    rows = read_png_rgb(src)
    h, w = len(rows), len(rows[0]) if rows else 0
    if not h or not w:
        write_png_rgb(dest, rows)
        return dest

    bg = [[False] * w for _ in range(h)]
    stack = []
    for x in range(w):
        stack.append((0, x))
        stack.append((h - 1, x))
    for y in range(h):
        stack.append((y, 0))
        stack.append((y, w - 1))
    while stack:
        y, x = stack.pop()
        if y < 0 or y >= h or x < 0 or x >= w or bg[y][x]:
            continue
        if not _is_chroma_px(rows[y][x], chroma):
            continue
        bg[y][x] = True
        stack.append((y - 1, x))
        stack.append((y + 1, x))
        stack.append((y, x - 1))
        stack.append((y, x + 1))

    ymin, ymax, xmin, xmax = h, -1, w, -1
    for y, row in enumerate(rows):
        for x in range(w):
            if not bg[y][x]:
                if y < ymin:
                    ymin = y
                if y > ymax:
                    ymax = y
                if x < xmin:
                    xmin = x
                if x > xmax:
                    xmax = x
    if ymax < ymin:
        write_png_rgb(dest, rows)
        return dest
    pad = max(0, int(pad))
    ymin = max(0, ymin - pad)
    ymax = min(h - 1, ymax + pad)
    xmin = max(0, xmin - pad)
    xmax = min(w - 1, xmax + pad)
    cropped = []
    for y in range(ymin, ymax + 1):
        cropped.append([
            fill if bg[y][x] else rows[y][x][:3]
            for x in range(xmin, xmax + 1)
        ])
    write_png_rgb(dest, cropped)
    return dest


def find_chrome():
    env = os.environ.get("CHROME_BIN") or os.environ.get("GOOGLE_CHROME_BIN")
    if env and Path(env).exists():
        return Path(env)
    for name in ("google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return Path(found)
    for p in (
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ):
        if p.exists():
            return p
    return None


CHROME_OFFLINE_FLAGS = (
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-sync",
    "--disable-default-apps",
    "--disable-domain-reliability",
    "--disable-extensions",
    "--disable-client-side-phishing-detection",
    "--disable-breakpad",
    "--disable-features=OptimizationHints,MediaRouter,Translate,AutofillServerCommunication",
    "--no-pings",
    "--no-default-browser-check",
    "--metrics-recording-only",
    "--host-resolver-rules=MAP * ~NOTFOUND",
    "--proxy-server=http://127.0.0.1:9",
)


def _png_complete(path):
    try:
        data = Path(path).read_bytes()
    except OSError:
        return False
    return data[:8] == PNG_SIG and data.endswith(PNG_IEND)


def render_card_png(fragment, dest, chrome=None, force=False, sources=()):
    """Rasterize the HTML card to a tightly cropped PNG. Local Chrome only,
    launched with its background services and name resolution switched off;
    the page itself carries a CSP that allows only inline styles and data:
    images."""
    chrome = Path(chrome) if chrome else find_chrome()
    if chrome is None:
        return None
    dest = Path(dest)
    page = html_page_for_png(fragment)
    with tempfile.TemporaryDirectory(prefix="tc-png-") as td:
        td = Path(td)
        html_path = td / "card.html"
        raw_png = td / "shot.png"
        html_path.write_text(page, encoding="utf-8")
        profile = td / "chrome-profile"
        profile.mkdir()
        cmd = [
            str(chrome),
            "--headless",
            "--disable-gpu",
            "--no-first-run",
            *CHROME_OFFLINE_FLAGS,
            f"--user-data-dir={profile}",
            f"--screenshot={raw_png}",
            "--window-size=720,2400",
            "--virtual-time-budget=4000",
            html_path.resolve().as_uri(),
        ]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = time.time() + 20
        try:
            # done when Chrome exits, or once the file is a whole PNG (IEND);
            # a file that merely exists may still be mid-write
            while time.time() < deadline:
                if proc.poll() is not None or _png_complete(raw_png):
                    break
                time.sleep(0.1)
            else:
                raise TimeoutError("chrome screenshot timed out")
        finally:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    proc.kill()
                proc.wait(timeout=5)
        if not raw_png.exists():
            raise FileNotFoundError("chrome did not write a screenshot")
        if not _png_complete(raw_png):
            raise ValueError("chrome wrote an incomplete screenshot")
        cropped = td / "card.png"
        crop_png_chroma(raw_png, cropped)
        write_output(dest, cropped.read_bytes(), force=force, sources=sources)
    return dest


def open_preview(path):
    if os.environ.get("TERMINALLY_COOKED_NO_OPEN"):
        return
    path = str(path)
    if sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    elif shutil.which("xdg-open"):
        subprocess.run(["xdg-open", path], check=False)


def projects_dir(override=None):
    """Transcript root: --projects-dir flag > $CLAUDE_CONFIG_DIR/projects > default."""
    if override:
        return Path(override).expanduser()
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return Path(env).expanduser() / "projects"
    return PROJECTS_DIR


def share_caption(s, buffs, final):
    """Suggested post text from allowlisted fields only. Copied locally; the
    user pastes and posts — the score never rides a URL to anyone's server."""
    core, flat = score_parts(s, buffs)
    top = " · ".join(f"{ICONS.get(n, '·')} {clean(n)}" for n, k, v, _ in buffs[:3])
    return (f"Terminally Cooked: +{final:,} (skill {core:,} · comedy {flat:,}) — {division(s)}\n"
            f"{top}\n(means nothing. sharing it anyway.) #TerminallyCooked")


def default_home():
    return Path(os.environ.get("TERMINALLY_COOKED_HOME") or Path.home())


INVOKER_ENV = (
    "GROK_SESSION_ID",
    "CODEX_THREAD_ID",
    "CODEX_SESSION_ID",
    "CLAUDE_SESSION_ID",
    "CLAUDE_CODE_SESSION_ID",
)


def invoking_ids(env=None):
    """Session/thread ids the current process belongs to. Empty if unknown."""
    env = os.environ if env is None else env
    ids = []
    for key in INVOKER_ENV:
        v = env.get(key)
        if isinstance(v, str) and v.strip():
            ids.append(v.strip())
    return ids


def is_invoking_session(path, live_ids):
    if not live_ids:
        return False
    label = session_label(path)
    name = Path(path).name.lower()
    for i in live_ids:
        i = i.strip().lower()
        if not i:
            continue
        if label and (label == i or (len(i) >= 8 and label.startswith(i))
                      or (len(label) == 8 and i.startswith(label))):
            return True
        if len(i) >= 8 and i in name:
            return True
    return False


def claude_project_slug(cwd):
    """Claude Code project folder: every non-alphanumeric char becomes '-'."""
    return "".join(ch if ch.isalnum() else "-" for ch in str(Path(cwd)))


def _store_kind(p):
    p = Path(p)
    if p.is_dir():
        return "grok"
    if p.name.startswith("rollout-"):
        return "codex"
    if p.name.startswith("session-") and p.parent.name == "chats":
        return "gemini"
    return "claude-code"


def live_paths(cands, live_ids=None, env=None, cwd=None):
    """(sessions to exclude, heuristic?). Pass the UNFILTERED session list.

    A recognized invoker id that matches a session is identity: only that
    session is excluded. Otherwise the exclusion is a conservative guess,
    never proof: the newest session of every harness store, plus the newest
    Claude transcript in this cwd's project folder."""
    env = os.environ if env is None else env
    if live_ids is None:
        live_ids = invoking_ids(env)
    matched = [p for p in cands if is_invoking_session(p, live_ids)]
    if matched:
        return matched, False
    newest = {}
    for p in cands:
        kind = _store_kind(p)
        if kind not in newest or session_mtime(p) > session_mtime(newest[kind]):
            newest[kind] = p
    out = list(newest.values())
    slug = claude_project_slug(cwd or Path.cwd())
    same = [p for p in cands if p.suffix == ".jsonl" and p.parent.name == slug]
    if same:
        out.append(max(same, key=session_mtime))
    seen, uniq = set(), []
    for p in out:
        if p.resolve() not in seen:
            seen.add(p.resolve())
            uniq.append(p)
    return uniq, True


def display_label(path):
    return session_label(path) or "unnamed"


def juice_score(s):
    """How much of a session there is to roast. Not the entertainment score.

    Unknown Codex outcomes count as activity (they are real tool calls).
    Sub-5-minute sessions score near-zero so a fat probe cannot beat a
    shorter real work session. Probes only win if nothing longer exists.
    """
    tools = s["green"] + s["red"] + s.get("unknown_results", 0)
    if tools == 0:
        return 0
    mins = duration_minutes(s) or 1
    if mins < 5:
        return tools * 1e-6
    length = 1.0 if mins >= 15 else 0.45
    return tools * length


def pick_juicy_session(home=None, now=None, claude_projects=None, live_ids=None,
                      env=None, cwd=None):
    """Return (path, note). Excludes the invoking session by id when the
    harness exposes one (INVOKER_ENV); otherwise excludes the newest session
    per harness and in this project, and the note says it was a heuristic."""
    home = Path(home or default_home())
    now = now or datetime.now().astimezone()
    today = now.astimezone().date()
    every = list_sessions(home, claude_projects)
    if not every:
        return None, "no session transcripts found"
    live, heuristic = live_paths(every, live_ids, env=env, cwd=cwd)
    live_resolved = {p.resolve() for p in live}
    skipped = ", ".join(clean(display_label(p)) for p in live) or "none"
    if heuristic:
        lead = ("no invoker session id recognized; skipped the newest session per harness "
                f"and in this project as possible live sessions (heuristic, not identity proof): {skipped}")
    else:
        lead = f"skipped the live invoking session {skipped}"
    rest = [p for p in every
            if p.resolve() not in live_resolved and session_bytes(p) <= MAX_PICK_BYTES]
    if not rest:
        return None, f"{lead}; nothing else to grade"
    cutoff = now.timestamp() - PICK_LOOKBACK_DAYS * 86400
    recent = [p for p in rest if session_mtime(p) >= cutoff] or rest
    midnight = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    today_files = sorted((p for p in rest if session_mtime(p) >= midnight),
                         key=session_mtime, reverse=True)
    lookback_recent = sorted(recent, key=session_mtime, reverse=True)
    shortlist, seen = [], set()
    for p in today_files + lookback_recent:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        shortlist.append(p)
        if len(shortlist) >= PICK_ANALYZE_CAP:
            break
    scored = []
    for p in shortlist:
        try:
            stats = analyze(p)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        scored.append((p, stats, juice_score(stats)))
    if not scored:
        return None, f"{lead}; no readable sessions"

    def is_probe(stats):
        mins = duration_minutes(stats) or 1
        return mins < 5
    real = [(p, st, j) for p, st, j in scored if j > 0 and not is_probe(st)]
    probes = [(p, st, j) for p, st, j in scored if j > 0 and is_probe(st)]

    def take(rows, days):
        out = []
        for p, stats, j in rows:
            when = parse_ts(stats.get("first_ts"))
            if when is not None:
                age = (today - when.astimezone().date()).days
            else:
                age = (today - datetime.fromtimestamp(session_mtime(p)).date()).days
            if 0 <= age <= days:
                out.append((p, stats, j))
        return out
    chosen = (take(real, 0) or take(real, PICK_LOOKBACK_DAYS)
              or take(probes, 0) or take(probes, PICK_LOOKBACK_DAYS))
    if not chosen:
        return None, f"{lead}; no other sessions today or in the last {PICK_LOOKBACK_DAYS} days"
    path, stats, _ = max(chosen, key=lambda t: t[2])
    tools = stats["green"] + stats["red"] + stats.get("unknown_results", 0)
    return path, f"{lead}; picked {clean(display_label(path))} ({tools} results)"


def _refuse_invoker(p):
    sys.exit(f"refusing to grade the invoking session {clean(display_label(p))}: "
             "its id matches this process's harness session id. Name a different session.")


def find_session(arg, root=None, home=None, claude_projects=None, env=None):
    live_ids = invoking_ids(env)
    if arg and Path(arg).exists():
        p = Path(arg)
        if is_invoking_session(p, live_ids):
            _refuse_invoker(p)
        return p, None
    home = Path(home or default_home())
    claude_projects = claude_projects or root
    if arg:  # id prefix match across harnesses
        want = arg.strip().lower()
        for p in list_sessions(home, claude_projects):
            label = session_label(p)
            if (label and (label.startswith(want) or (len(label) == 8 and want.startswith(label)))) \
                    or p.name.startswith(arg):
                if is_invoking_session(p, live_ids):
                    _refuse_invoker(p)
                return p, None
        sys.exit(f"no session matching '{clean(arg)}'")
    path, note = pick_juicy_session(home=home, claude_projects=claude_projects,
                                    live_ids=live_ids, env=env)
    if path is None:
        sys.exit(note)
    return path, note


class OutputError(Exception):
    pass


def session_sources(path, harness):
    """Resolved files that make up the graded session, plus a Grok dir root."""
    _, files = session_identity(path, harness)
    out = {Path(path).resolve()} | {Path(f).resolve() for f in files}
    if Path(path).is_dir():
        out |= {f.resolve() for f in Path(path).rglob("*")}
    return out


def check_output(dest, force=False, sources=()):
    dest = Path(dest)
    resolved = dest.resolve()
    if resolved in set(sources):
        raise OutputError(f"refusing to write over a source session file: {clean(dest)}")
    if any(src.is_dir() and resolved.is_relative_to(src) for src in sources):
        raise OutputError(f"refusing to write inside the source session: {clean(dest)}")
    if os.path.lexists(dest):
        if not force:
            kind = "is a symlink" if os.path.islink(dest) else "already exists"
            raise OutputError(f"{clean(dest)} {kind}; pass --force to replace it")
        if dest.is_dir() and not os.path.islink(dest):
            raise OutputError(f"{clean(dest)} is a directory")
    if not dest.parent.is_dir():
        raise OutputError(f"no such directory for {clean(dest)}")


def write_output(dest, data, force=False, sources=()):
    """Atomic write in the destination's directory. Never follows a symlink
    destination (the link itself is replaced under --force) and never
    replaces an existing file without --force."""
    dest = Path(dest)
    check_output(dest, force, sources)
    if isinstance(data, str):
        data = data.encode("utf-8")
    fd, tmp = tempfile.mkstemp(dir=str(dest.parent), prefix=".tc-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        mask = os.umask(0)
        os.umask(mask)
        os.chmod(tmp, 0o666 & ~mask)    # mkstemp's 0600 would make a share card private
        if force:
            os.replace(tmp, dest)
        else:
            try:
                os.link(tmp, dest)          # atomic create: fails if dest appeared
            except FileExistsError:
                raise OutputError(f"{clean(dest)} already exists; pass --force to replace it")
            except OSError:
                if os.path.lexists(dest):
                    raise OutputError(f"{clean(dest)} already exists; pass --force to replace it")
                os.replace(tmp, dest)
    finally:
        if os.path.lexists(tmp):
            os.unlink(tmp)
    return dest


def main():
    ap = argparse.ArgumentParser(description=(
        "Grade one of your own AI-coding sessions into a comedy results card "
        "(local-only, zero-upload). With no session argument it auto-picks a juicy "
        "session from today. When the invoking harness exposes its session id ("
        + ", ".join(INVOKER_ENV) + ") that session is excluded by id; otherwise the "
        "newest session per harness and in this project are excluded as a heuristic, "
        "and the pick note says so."))
    ap.add_argument("session", nargs="?", help=(
        "Path to a session file/dir, or a session-id prefix. A target whose id matches "
        "this process's harness session id is refused. Omit to auto-pick."))
    ap.add_argument("--html", nargs="?", const="", metavar="OUT",
                    help="Also write a shareable standalone HTML card (default: ./terminally-cooked-card-<id>.html)")
    ap.add_argument("--png", nargs="?", const="", metavar="OUT",
                    help="Write a tightly cropped PNG of the card and open it (also writes HTML). "
                         "Local Chrome, launched with background networking and name resolution off; nothing is uploaded.")
    ap.add_argument("--force", action="store_true",
                    help="Replace an existing --html/--png destination (a symlink is replaced, never followed)")
    ap.add_argument("--tz", metavar="ZONE",
                    help="Zone for Night Shift hours: UTC, an offset like UTC-07:00, or an IANA name "
                         "(default: local offset at the session's first timestamp). Stamped on the "
                         "card; pass the stamped value back to reproduce a score.")
    ap.add_argument("--share", action="store_true",
                    help="Copy a suggested post caption to the clipboard and open a blank X composer. Nothing is transmitted; you paste and post.")
    ap.add_argument("--projects-dir", metavar="DIR",
                    help="Claude Code transcript root (default: $CLAUDE_CONFIG_DIR/projects or ~/.claude/projects). Auto-pick still scans Grok/Codex/Gemini under $HOME.")
    args = ap.parse_args()
    try:
        zone = parse_zone(args.tz) if args.tz else None
    except ValueError as exc:
        ap.error(str(exc))
    claude_root = projects_dir(args.projects_dir)
    path, note = find_session(args.session, claude_root, home=default_home(),
                              claude_projects=claude_root)
    if note:
        print(clean(note), file=sys.stderr)
    harness = detect_harness(path) or "claude-code"
    try:
        s = analyze(path, harness, tz=zone)
    except (OSError, ValueError) as exc:
        sys.exit(f"could not read session: {clean(exc)}")
    buffs = pick_buffs(s)
    final = score(s, buffs)
    print(render(s, buffs, final))
    sid = card_fields(s)["sid"]
    sources = session_sources(path, harness)
    html_out = png_out = None
    if args.html is not None or args.png is not None:
        html_out = Path(args.html) if args.html else Path(f"terminally-cooked-card-{sid}.html")
    if args.png is not None:
        png_out = Path(args.png) if args.png else html_out.with_suffix(".png")
    try:
        for dest in (html_out, png_out):
            if dest is not None:
                check_output(dest, args.force, sources)
        if html_out and png_out and html_out.resolve() == png_out.resolve():
            raise OutputError("--html and --png name the same file")
    except OutputError as exc:
        sys.exit(f"not writing card: {exc}")
    html_text = None
    if html_out is not None:
        html_text = render_html(s, buffs, final)
        try:
            write_output(html_out, html_text, args.force, sources)
        except (OutputError, OSError) as exc:
            sys.exit(f"not writing card: {clean(exc)}")
        print(f"\nhtml card: {clean(html_out)}")
    if png_out is not None:
        try:
            written = render_card_png(html_text, png_out, force=args.force, sources=sources)
        except (OSError, ValueError, OutputError, subprocess.SubprocessError) as exc:
            print(f"png card failed: {clean(exc)}", file=sys.stderr)
            written = None
        if written is None and find_chrome() is None:
            print("png card: no local Chrome/Chromium found; HTML was written instead",
                  file=sys.stderr)
        elif written is not None:
            print(f"png card: {clean(written)}")
            open_preview(written)
    if args.share:
        caption = share_caption(s, buffs, final)
        print("\nsuggested caption:\n" + caption)
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=caption.encode(), check=False)
            print("(copied to clipboard)")
            subprocess.run(["open", "https://x.com/compose/post"], check=False)


if __name__ == "__main__":
    main()
