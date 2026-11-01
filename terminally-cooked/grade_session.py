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
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

from harness_adapters import (
    detect_harness, iter_events, session_identity,
    list_sessions, session_mtime, session_bytes,
)

SCORING_VERSION = "scoring-v0.5 (entertainment only)"
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
TALLY_RE = re.compile(r"(\d+)\s+passed(?:,?\s+(\d+)\s+fail(?:ed|ures?))?", re.IGNORECASE)
OVERLOAD_RE = re.compile(r"overloaded|\b529\b", re.IGNORECASE)
# Tallies only count when the producing Bash command looks like a test run —
# otherwise quoted/echoed test numbers (docs, cards, logs) poison the delta.
TEST_CMD_RE = re.compile(
    r"pytest|py\.test|unittest|npm (?:run )?(?:test|e2e)|yarn test|pnpm test"
    r"|go test|cargo test|make test|mvn test|gradle test|playwright|cypress"
    r"|jest|vitest|phpunit|rspec|ctest|test_|_test|run_suite", re.IGNORECASE)
INTERRUPT_MARKER = "[Request interrupted"


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


def analyze(path, harness=None):
    """Grade one session from any supported harness. Detection is automatic;
    parsing is delegated to harness_adapters, bookkeeping happens here."""
    harness = harness or detect_harness(path) or "claude-code"
    session_id, hash_paths = session_identity(path, harness)
    sha = hashlib.sha256()
    for hash_path in hash_paths:
        name = Path(hash_path).name.encode()
        sha.update(len(name).to_bytes(4, "big"))
        sha.update(name)
        size = Path(hash_path).stat().st_size
        sha.update(size.to_bytes(8, "big"))
        with open(hash_path, "rb") as fh:      # chunked: transcripts can be huge
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                sha.update(chunk)
    s = {
        "session_id": session_id,
        "harness": harness,
        "transcript_sha": sha.hexdigest(),
        "models": {},
        "efforts": {},
        "tools": {},
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
    for ev in iter_events(path, harness):
        ts = ev.get("ts")
        if ts:
            s["first_ts"] = s["first_ts"] or ts
            s["last_ts"] = ts
            try:
                hour = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().hour
                if 2 <= hour < 6:
                    s["night_events"] += 1
            except ValueError:
                pass
        kind = ev["kind"]
        if kind == "compaction":
            s["compactions"] += 1
        elif kind == "permission":
            if ev["mode"] == "bypass":
                s["yolo_mode"] = True
            elif ev["mode"] == "plan":
                s["plan_entries"] += 1
        elif kind == "model":
            if ev.get("model"):
                s["models"][ev["model"]] = s["models"].get(ev["model"], 0) + 1
            if ev.get("effort"):
                s["efforts"][ev["effort"]] = s["efforts"].get(ev["effort"], 0) + 1
        elif kind == "usage":
            s["tokens_in"] += ev.get("input", 0)
            s["tokens_out"] += ev.get("output", 0)
        elif kind == "human":
            s["user_prompts"] += 1
            cook = 0
        elif kind == "interrupt":
            s["interruptions"] += 1
        elif kind == "tool_call":
            name = ev.get("name", "?")
            s["tools"][name] = s["tools"].get(name, 0) + 1
            if isinstance(ev.get("command"), str):
                pending[ev.get("id")] = ev["command"].strip()
        elif kind == "tool_result":
            success = ev.get("success")
            if ts and s["first_ts"] and success is not None:
                # unknown outcomes must not populate "clean" windows either —
                # they touch neither positive nor negative chains, anywhere
                try:
                    t0 = datetime.fromisoformat(s["first_ts"].replace("Z", "+00:00"))
                    tn = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    wi = int((tn - t0).total_seconds() // WINDOW_SECS)
                    if wi >= 0:  # out-of-order timestamps never land in a bucket
                        w = windows.setdefault(wi, [0, 0])
                        w[0] += 1
                        if success is False:
                            w[1] += 1
                except ValueError:
                    pass
            cmd = pending.pop(ev.get("id"), None)
            text = ev.get("text", "")
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
            if success is not None and cmd is not None and TEST_CMD_RE.search(cmd):
                m = TALLY_RE.search(text)
                if m:
                    tally = (int(m.group(1)), int(m.group(2) or 0))
                    # per-command tracking: deltas only compare like with like,
                    # so a full-suite run followed by one focused test can't
                    # register as a fictional regression
                    entry = tallies.setdefault(" ".join(cmd.split()), [tally, tally, 0])
                    entry[1] = tally
                    entry[2] += 1
    # pick the tally pair from the most-sampled test command (>=2 samples),
    # so first/last always describe the same suite
    picked = max(tallies.values(), key=lambda e: e[2], default=None)
    if picked and picked[2] >= 2:
        s["first_tally"], s["last_tally"] = picked[0], picked[1]
    elif picked:
        s["first_tally"] = s["last_tally"] = picked[1]   # single run: shown, no delta
    # only COMPLETED windows qualify: the in-progress final bucket is excluded,
    # so "three 20-minute windows" cannot be earned in twenty-one minutes
    last_bucket = max(windows) if windows else -1
    run = best = sparse = 0
    for i in range(last_bucket):
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


def safe_meta(value, limit=40):
    """Model/effort names come from the transcript and are untrusted for
    rendering: strip to a conservative charset before ANSI or HTML output."""
    return SAFE_META_RE.sub("", str(value))[:limit]


def meta_names(d):
    return ", ".join(safe_meta(k) for k in sorted(d, key=d.get, reverse=True))


def duration_minutes(s):
    try:
        t0 = datetime.fromisoformat(s["first_ts"].replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(s["last_ts"].replace("Z", "+00:00"))
        return max(1, int((t1 - t0).total_seconds() // 60))
    except (AttributeError, ValueError, TypeError):
        return None


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
    n = s["tools"].get("Agent", 0)
    return f"delegation: {n} subagent call(s) · internals not graded" if n else None


def pick_buffs(s):
    """The modifier catalog. Three kinds:
    - "chain": multiplies — earned only by serialized sustained success
    - "debuff": multiplies down — errors are always real
    - "flavor": flat point bonus — context/comedy, never compounds
    Values are jokes, not measurement."""
    buffs = []  # (name, kind, value, line)
    total = s["green"] + s["red"]
    tools = s["tools"]
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
    if tools.get("AskUserQuestion", 0) >= 4:
        buffs.append(("Twenty Questions", "debuff", 0.9, f"asked the human {tools['AskUserQuestion']} times"))
    if s["interruptions"] >= 3:
        buffs.append(("Backseat Driver", "debuff", 0.8, f"human slammed the brakes {s['interruptions']} times"))
    if s["plan_entries"] >= 1 and tools.get("Edit", 0) + tools.get("Write", 0) == 0:
        buffs.append(("All Plan No Game", "debuff", 0.8, f"entered plan mode {s['plan_entries']}x, zero Edit/Write calls"))
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
    if tools.get("Agent", 0) >= 5:
        buffs.append(("Middle Manager", "flavor", 150, f"delegated to {tools['Agent']} subagents"))
    if s["compactions"] >= 1:
        buffs.append(("Lost the Tapes", "flavor", 100, f"survived {s['compactions']} compaction(s); records incomplete"))
    if len(s["models"]) >= 3:
        buffs.append(("Model Hopper", "flavor", 100, f"{len(s['models'])} different models in one session"))
    reads, bashes = tools.get("Read", 0), tools.get("Bash", 0)
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
    mins = duration_minutes(s)
    dur = f"{mins // 60}h {mins % 60}m" if mins else "unknown"
    date = (s["first_ts"] or "")[:10]
    models = meta_names(s["models"])
    efforts = meta_names(s["efforts"])
    w = 62
    line = "─" * w
    out = []
    out.append(C.dim("┌" + line + "┐"))
    out.append(C.bold("  TERMINALLY COOKED") + C.dim(f"  ·  session {s['session_id'][:8]}  ·  {date}  ·  {dur}  ·  {division(s)}"))
    out.append(C.dim(f"  {models}  ·  effort: {efforts}"))
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
    tool_bits = "  ".join(f"{k}:{v}" for k, v in sorted(s["tools"].items(), key=lambda kv: -kv[1])[:6])
    out.append(C.dim(f"  {tool_bits}"))
    if s["tokens_in"] or s["tokens_out"]:
        out.append(C.dim(f"  tokens: {s['tokens_in']/1e6:,.1f}M in · {s['tokens_out']/1e6:,.2f}M out"))
    out.append(C.dim("├" + line + "┤"))
    for name, kind, value, why in buffs:
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
    out.append(C.dim(f"  {SCORING_VERSION} · adapter {s.get('harness', 'claude-code')} · {fingerprint(s)}"))
    out.append(C.dim("└" + line + "┘"))
    return "\n".join(out)


def fingerprint(s):
    """Verification stamp: recomputing with the official script on the same
    transcript must reproduce the score. Detects edited numbers and modified
    scoring code; does not prove the transcript itself is genuine."""
    code = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:8]
    return f"recompute: transcript {s['transcript_sha'][:12]} · code {code}"


def render_html(s, buffs, final):
    """Standalone shareable card. Same field allowlist as the ANSI card."""
    mins = duration_minutes(s)
    dur = f"{mins // 60}h {mins % 60}m" if mins else "unknown"
    date = (s["first_ts"] or "")[:10]
    models = meta_names(s["models"])
    efforts = meta_names(s["efforts"])
    total = s["green"] + s["red"]
    pct = round(100 * s["green"] / total) if total else 0
    esc = html_mod.escape

    def chip(name, kind, value, why):
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
    logo = logo_data_uri()
    header = (f'<img class="wordmark" src="{logo}" alt="TERMINALLY COOKED">'
              if logo else "<h1>TERMINALLY COOKED</h1>")
    return f"""<!-- terminally-cooked shareable card -->
<meta charset="utf-8">
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
<div class="counts"><span class="g">+{s['green']}</span> <span class="lbl">tool results</span> &middot; <span class="r">{s['red']}</span> <span class="lbl">errors</span> &middot; <span class="y">streak {s['longest_streak']}</span></div>
<div class="meter">
<div class="fever"><i></i></div>
{tally}</div>
{tokens}
</div>
<div class="meta quiet">session {esc(s['session_id'][:8])} &middot; {esc(date)} &middot; {dur} &middot; {division(s)}</div>
<div class="meta quiet">{esc(models)} &middot; effort: {esc(efforts)}</div>
{f'<div class="meta quiet">{esc(note)}</div>' if note else ''}
{rows}
<div class="fine">{SCORING_VERSION} &middot; adapter {esc(s.get('harness', 'claude-code'))} &middot; {fingerprint(s)}</div>
</div></div>
"""


PNG_SIG = b"\x89PNG\r\n\x1a\n"
PNG_CHROMA = (255, 0, 255)          # screenshot key; not used in the card
PNG_FILL = (255, 204, 0)            # #ffcc00 — same as the yellow card; pad is the card, not a frame
PNG_PAD = 24                        # keep rounded corners off the PNG edge; pad matches the card, not a mat


def html_page_for_png(fragment):
    """Full document for rasterizing: magenta key around the card."""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
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
    """Read an 8-bit RGB or RGBA PNG into rows of (r,g,b)."""
    data = Path(path).read_bytes()
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


def render_card_png(fragment, dest, chrome=None):
    """Rasterize the HTML card to a tightly cropped PNG. Local Chrome only."""
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
            while time.time() < deadline:
                if raw_png.exists() and raw_png.stat().st_size > 100:
                    time.sleep(0.4)
                    break
                if proc.poll() is not None:
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
        if not raw_png.exists() or raw_png.stat().st_size < 100:
            raise FileNotFoundError("chrome did not write a screenshot")
        crop_png_chroma(raw_png, dest)
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
    top = " · ".join(f"{ICONS.get(n, '·')} {n}" for n, k, v, _ in buffs[:3])
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
    name = Path(path).name
    for i in live_ids:
        if i == label or i in name or name.startswith(i) or label.startswith(i):
            return True
    return False


def claude_project_slug(cwd):
    """Claude Code project folder: every non-alphanumeric char becomes '-'."""
    return "".join(ch if ch.isalnum() else "-" for ch in str(Path(cwd)))


def live_paths(cands, live_ids=None, env=None, cwd=None):
    """Sessions this process is currently writing. Env ids win.

    Claude Code often has no session-id env: fall back to the newest jsonl in
    this cwd's project folder. Last resort is global newest mtime.
    """
    env = os.environ if env is None else env
    if live_ids is None:
        live_ids = invoking_ids(env)
    matched = [p for p in cands if is_invoking_session(p, live_ids)]
    slug = claude_project_slug(cwd or Path.cwd())
    same = [p for p in cands if p.suffix == ".jsonl" and p.parent.name == slug]
    if same:
        newest_here = max(same, key=session_mtime)
        if newest_here.resolve() not in {p.resolve() for p in matched}:
            matched.append(newest_here)
    if matched:
        return matched
    if cands:
        return [max(cands, key=session_mtime)]
    return []


def session_label(path):
    p = Path(path)
    return p.name if p.is_dir() else p.stem[-36:] if len(p.stem) >= 36 else p.stem


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
    """Return (path, skip-note). Never returns the invoking session.

    live_ids come from harness env (GROK_SESSION_ID, CODEX_THREAD_ID, …).
    When those are absent, fall back to cwd-scoped Claude then newest mtime.
    """
    home = Path(home or default_home())
    now = now or datetime.now().astimezone()
    today = now.astimezone().date()
    cands = [p for p in list_sessions(home, claude_projects) if session_bytes(p) <= MAX_PICK_BYTES]
    if not cands:
        return None, "no session transcripts found"
    live = live_paths(cands, live_ids, env=env, cwd=cwd)
    live_resolved = {p.resolve() for p in live}
    rest = [p for p in cands if p.resolve() not in live_resolved]
    skipped = ", ".join(session_label(p) for p in live) or "live session"
    if not rest:
        return None, f"skipped live session {skipped}; nothing else to grade"
    cutoff = now.timestamp() - PICK_LOOKBACK_DAYS * 86400
    recent = [p for p in rest if session_mtime(p) >= cutoff] or rest
    midnight = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    today_files = [p for p in rest if session_mtime(p) >= midnight]
    lookback_recent = sorted(recent, key=session_mtime, reverse=True)[:PICK_ANALYZE_CAP]
    shortlist, seen = [], set()
    for p in today_files + lookback_recent:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        shortlist.append(p)
    scored = []
    for p in shortlist:
        try:
            stats = analyze(p)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        scored.append((p, stats, juice_score(stats)))
    if not scored:
        return None, f"skipped live session {skipped}; no readable sessions"
    def is_probe(stats):
        mins = duration_minutes(stats) or 1
        return mins < 5
    real = [(p, st, j) for p, st, j in scored if j > 0 and not is_probe(st)]
    probes = [(p, st, j) for p, st, j in scored if j > 0 and is_probe(st)]
    def take(rows, days):
        out = []
        for p, stats, j in rows:
            ts = stats.get("first_ts")
            try:
                when = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
                age = (today - when.date()).days
            except (ValueError, TypeError, AttributeError):
                age = (today - datetime.fromtimestamp(session_mtime(p)).date()).days
            if 0 <= age <= days:
                out.append((p, stats, j))
        return out
    chosen = (take(real, 0) or take(real, PICK_LOOKBACK_DAYS)
              or take(probes, 0) or take(probes, PICK_LOOKBACK_DAYS))
    if not chosen:
        return None, f"skipped live session {skipped}; no other sessions today or in the last {PICK_LOOKBACK_DAYS} days"
    path, stats, _ = max(chosen, key=lambda t: t[2])
    tools = stats["green"] + stats["red"] + stats.get("unknown_results", 0)
    note = (f"skipped live session {skipped}; "
            f"picked {session_label(path)} ({tools} results)")
    return path, note


def find_session(arg, root=None, home=None, claude_projects=None):
    if arg and Path(arg).exists():
        return Path(arg), None
    home = Path(home or default_home())
    claude_projects = claude_projects or root
    if arg:  # partial uuid match across harnesses
        for p in list_sessions(home, claude_projects):
            if session_label(p).startswith(arg) or p.name.startswith(arg):
                return p, None
        sys.exit(f"no session matching '{arg}'")
    path, note = pick_juicy_session(home=home, claude_projects=claude_projects)
    if path is None:
        sys.exit(note)
    return path, note


def main():
    ap = argparse.ArgumentParser(description="Grade one of your own AI-coding sessions into a comedy results card (local-only, zero-upload). With no path, picks a juicy session from today and never grades the live session that invoked this process.")
    ap.add_argument("session", nargs="?", help="Path to a session file/dir, a session-uuid prefix, or omit to auto-pick a juicy session from today (never the live invoking session)")
    ap.add_argument("--html", nargs="?", const="", metavar="OUT",
                    help="Also write a shareable standalone HTML card (default: ./terminally-cooked-card-<id>.html)")
    ap.add_argument("--png", nargs="?", const="", metavar="OUT",
                    help="Write a tightly cropped PNG of the card and open it (also writes HTML). Local Chrome only; nothing is uploaded.")
    ap.add_argument("--share", action="store_true",
                    help="Copy a suggested post caption to the clipboard and open a blank X composer. Nothing is transmitted; you paste and post.")
    ap.add_argument("--projects-dir", metavar="DIR",
                    help="Claude Code transcript root (default: $CLAUDE_CONFIG_DIR/projects or ~/.claude/projects). Auto-pick still scans Grok/Codex/Gemini under $HOME.")
    args = ap.parse_args()
    claude_root = projects_dir(args.projects_dir)
    path, note = find_session(args.session, claude_root, home=default_home(),
                              claude_projects=claude_root)
    if note:
        print(note, file=sys.stderr)
    s = analyze(path)
    buffs = pick_buffs(s)
    final = score(s, buffs)
    print(render(s, buffs, final))
    html_text = None
    html_out = None
    if args.html is not None or args.png is not None:
        html_text = render_html(s, buffs, final)
        html_out = Path(args.html) if args.html else Path(
            f"terminally-cooked-card-{s['session_id'][:8]}.html")
        html_out.write_text(html_text)
        print(f"\nhtml card: {html_out}")
    if args.png is not None:
        png_out = Path(args.png) if args.png else (
            html_out.with_suffix(".png") if html_out
            else Path(f"terminally-cooked-card-{s['session_id'][:8]}.png"))
        try:
            written = render_card_png(html_text, png_out)
        except (OSError, ValueError, subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"png card failed: {exc}", file=sys.stderr)
            written = None
        if written is None and find_chrome() is None:
            print("png card: no local Chrome/Chromium found; HTML was written instead",
                  file=sys.stderr)
        elif written is not None:
            print(f"png card: {written}")
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
