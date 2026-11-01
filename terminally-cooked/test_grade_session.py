#!/usr/bin/env python3
"""Regression tests for grade_session.py against a synthetic fixture transcript."""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from grade_session import analyze, pick_buffs, score, render_html

TS = "2026-08-19T03:{m:02d}:00.000Z"  # 03:xx UTC — hour depends on local tz; night test overrides


def asst(blocks, model="claude-sonnet-5", effort="high", ts="2026-08-19T10:00:00.000Z", usage=None):
    return {"type": "assistant", "timestamp": ts, "effort": effort,
            "message": {"model": model, "content": blocks, "usage": usage or {}}}


def tool_use(name, tid, **inp):
    return {"type": "tool_use", "name": name, "id": tid, "input": inp}


def result(tid, text="", err=False, ts="2026-08-19T10:01:00.000Z"):
    return {"type": "user", "timestamp": ts,
            "message": {"content": [{"type": "tool_result", "tool_use_id": tid,
                                     "is_error": err, "content": text}]}}


def prompt(text="do the thing", ts="2026-08-19T09:59:00.000Z"):
    return {"type": "user", "timestamp": ts, "message": {"content": text}}


def write_fixture(records):
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    for r in records:
        f.write(json.dumps(r) + "\n")
    f.close()
    return f.name


def buff_names(s):
    return {b[0] for b in pick_buffs(s)}


def test_basic_counts():
    recs = [prompt(),
            asst([tool_use("Bash", "t1", command="ls")]),
            result("t1", "ok"),
            asst([tool_use("Bash", "t2", command="pytest")]),
            result("t2", "12 passed, 3 failed"),
            asst([tool_use("Bash", "t3", command="pytest")]),
            result("t3", "15 passed, 0 failed"),
            asst([tool_use("Bash", "t4", command="bad")]),
            result("t4", "boom", err=True)]
    s = analyze(write_fixture(recs))
    assert s["green"] == 3 and s["red"] == 1, (s["green"], s["red"])
    assert s["longest_streak"] == 3
    assert s["first_tally"] == (12, 3) and s["last_tally"] == (15, 0)
    assert "Test Whisperer" in buff_names(s)


def test_doom_loop_same_command():
    recs = [prompt()]
    for i in range(3):
        recs.append(asst([tool_use("Bash", f"d{i}", command="make build")]))
        recs.append(result(f"d{i}", "error: no rule", err=True))
    s = analyze(write_fixture(recs))
    assert s["worst_doom_loop"] == 3, s["worst_doom_loop"]
    assert "Doom Loop" in buff_names(s)


def test_doom_loop_needs_identical_commands():
    recs = [prompt()]
    for i, cmd in enumerate(["make a", "make b", "make c"]):
        recs.append(asst([tool_use("Bash", f"d{i}", command=cmd)]))
        recs.append(result(f"d{i}", "err", err=True))
    s = analyze(write_fixture(recs))
    assert s["worst_doom_loop"] == 1
    assert "Doom Loop" not in buff_names(s)


def test_doom_loop_reset_by_success():
    recs = [prompt()]
    for i in range(2):
        recs.append(asst([tool_use("Bash", f"d{i}", command="make")]))
        recs.append(result(f"d{i}", "err", err=True))
    recs.append(asst([tool_use("Bash", "ok", command="make")]))
    recs.append(result("ok", "fine"))
    recs.append(asst([tool_use("Bash", "d9", command="make")]))
    recs.append(result("d9", "err", err=True))
    s = analyze(write_fixture(recs))
    assert s["worst_doom_loop"] == 2


def test_compaction_marker():
    recs = [prompt(),
            {"type": "user", "isCompactSummary": True, "timestamp": "2026-08-19T10:00:00.000Z",
             "message": {"content": [{"type": "text", "text": "summary"}]}}]
    recs += [asst([tool_use("Bash", f"g{i}", command="ls")]) for i in range(1)]
    recs += [result("g0", "ok")]
    s = analyze(write_fixture(recs))
    assert s["compactions"] == 1
    assert "Lost the Tapes" in buff_names(s)


def test_yolo_mode():
    recs = [{"type": "permission-mode", "permissionMode": "bypassPermissions"}, prompt()]
    s = analyze(write_fixture(recs))
    assert s["yolo_mode"] is True
    assert "YOLO MODE" in buff_names(s)


def test_let_it_cook():
    recs = [prompt()]
    for i in range(55):
        recs.append(asst([tool_use("Bash", f"c{i}", command=f"step {i}")]))
        recs.append(result(f"c{i}", "ok"))
    s = analyze(write_fixture(recs))
    assert s["longest_cook"] == 55
    assert "LET IT COOK" in buff_names(s)
    # a human text prompt resets the run
    recs.append(prompt("now stop"))
    recs.append(asst([tool_use("Bash", "z", command="ls")]))
    recs.append(result("z", "ok"))
    s2 = analyze(write_fixture(recs))
    assert s2["longest_cook"] == 55


def test_token_bonfire():
    recs = [prompt(), asst([tool_use("Bash", "t", command="ls")],
                           usage={"input_tokens": 10, "cache_read_input_tokens": 120_000_000,
                                  "output_tokens": 500}),
            result("t", "ok")]
    s = analyze(write_fixture(recs))
    assert s["tokens_in"] == 120_000_010
    assert "Token Bonfire" in buff_names(s)


def test_crop_png_chroma_tight():
    from grade_session import write_png_rgb, read_png_rgb, crop_png_chroma
    d = Path(tempfile.mkdtemp())
    src, dest = d / "in.png", d / "out.png"
    rows = [[(255, 0, 255)] * 20 for _ in range(20)]
    for y in range(7, 13):
        for x in range(7, 13):
            rows[y][x] = (13, 17, 23)
    write_png_rgb(src, rows)
    crop_png_chroma(src, dest, pad=0)
    out = read_png_rgb(dest)
    assert len(out) == 6 and len(out[0]) == 6
    assert all(px == (13, 17, 23) for row in out for px in row)


def test_png_fill_matches_card_ground():
    """Pad is the yellow card, not a separate cream frame around a dark card."""
    from grade_session import PNG_FILL
    assert PNG_FILL == (255, 204, 0)


def test_crop_png_chroma_keeps_padding():
    """Keep pad pixels of card fill around the rounded card so the border is not the PNG edge."""
    from grade_session import write_png_rgb, read_png_rgb, crop_png_chroma, PNG_FILL
    d = Path(tempfile.mkdtemp())
    src, dest = d / "in.png", d / "out.png"
    rows = [[(255, 0, 255)] * 80 for _ in range(80)]
    for y in range(30, 40):
        for x in range(30, 40):
            rows[y][x] = (48, 54, 61)
    write_png_rgb(src, rows)
    crop_png_chroma(src, dest, pad=8)
    out = read_png_rgb(dest)
    assert len(out) == 26 and len(out[0]) == 26
    assert out[0][0] == PNG_FILL and out[-1][-1] == PNG_FILL
    assert out[8][8] == (48, 54, 61)
    assert all(px != (255, 0, 255) for row in out for px in row)


def test_crop_png_chroma_fills_antialiased_fringe():
    """Chrome anti-aliases magenta into the rounded-corner AABB; those pixels
    must become the card fill, not a pink halo on the share PNG."""
    from grade_session import write_png_rgb, read_png_rgb, crop_png_chroma, PNG_FILL
    d = Path(tempfile.mkdtemp())
    src, dest = d / "in.png", d / "out.png"
    rows = [[(255, 0, 255)] * 24 for _ in range(24)]
    for y in range(8, 16):
        for x in range(8, 16):
            rows[y][x] = (13, 17, 23)
    # near-magenta fringe on the south-west / south-east corners, including
    # the darker anti-alias Chrome blends toward the card fill
    rows[15][8] = (246, 1, 247)
    rows[15][15] = (250, 1, 250)
    rows[14][7] = (186, 17, 190)
    rows[14][16] = (189, 16, 193)
    rows[13][6] = (131, 29, 138)
    rows[13][17] = (92, 39, 102)
    write_png_rgb(src, rows)
    crop_png_chroma(src, dest, pad=0)
    out = read_png_rgb(dest)
    assert len(out) == 8 and len(out[0]) == 8
    assert out[7][0] == PNG_FILL and out[7][7] == PNG_FILL
    assert all(px != (255, 0, 255) for row in out for px in row)
    assert all(not (px[0] > px[1] + 40 and px[2] > px[1] + 40 and abs(px[0] - px[2]) <= 50)
               for row in out for px in row)


def test_crop_png_chroma_keeps_interior_magenta():
    """Badge art may contain purple; only edge-connected chroma is keyed."""
    from grade_session import write_png_rgb, read_png_rgb, crop_png_chroma
    d = Path(tempfile.mkdtemp())
    src, dest = d / "in.png", d / "out.png"
    rows = [[(255, 0, 255)] * 20 for _ in range(20)]
    for y in range(6, 14):
        for x in range(6, 14):
            rows[y][x] = (13, 17, 23)
    rows[10][10] = (255, 0, 255)
    write_png_rgb(src, rows)
    crop_png_chroma(src, dest, pad=0)
    out = read_png_rgb(dest)
    assert out[4][4] == (255, 0, 255)


def test_html_page_for_png_uses_chroma_key():
    from grade_session import html_page_for_png
    page = html_page_for_png("<div class='lg-card'>hello</div>")
    assert "#ff00ff" in page and "lg-card" in page


def test_png_cli_if_chrome_available():
    from grade_session import find_chrome
    if find_chrome() is None:
        return
    recs = [prompt(), asst([tool_use("Bash", "t", command="ls")]), result("t", "ok")]
    fix = write_fixture(recs)
    d = Path(tempfile.mkdtemp())
    png = d / "card.png"
    env = os.environ.copy()
    env["TERMINALLY_COOKED_NO_OPEN"] = "1"
    out = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "grade_session.py"),
         fix, "--png", str(png)],
        capture_output=True, text=True, env=env, cwd=str(d),
    )
    assert out.returncode == 0, out.stderr
    assert png.exists() and png.stat().st_size > 100
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_html_tally_uses_claude_code_diff():
    """Share tally is a Claude Code +/- hunk, not a tinted `#` count line."""
    recs = [prompt(),
            asst([tool_use("Bash", "t2", command="pytest")]),
            result("t2", "12 passed, 3 failed"),
            asst([tool_use("Bash", "t3", command="pytest")]),
            result("t3", "15 passed, 0 failed")]
    s = analyze(write_fixture(recs))
    html = render_html(s, pick_buffs(s), 1)
    assert "- # " not in html
    assert "- 12 tests passed, 3 failed" in html
    assert "+ 15 tests passed, 0 failed" in html
    assert "tool results" in html
    assert ">green<" not in html
    assert "border-left:4px solid" in html
    assert "#ffecea" in html and "#dcfce7" in html
    assert 'class="meter"' in html
    assert html.index('class="meter"') < html.index('class="fever"')
    assert html.index('class="fever"') < html.index('class="diff"')
    assert "6px -22px" not in html
    assert html.index('class="meter"') < html.index("- 12 tests passed")


def test_html_share_card_score_leads():
    """Share card is score-first so a Telegram/X crop hits the joke, not the meta."""
    recs = [prompt(), asst([tool_use("Bash", "t", command="ls")]), result("t", "ok")]
    s = analyze(write_fixture(recs))
    html = render_html(s, pick_buffs(s), 12949)
    assert html.index('class="final"') < html.index('class="fever"')
    assert html.index('class="final"') < html.index('class="badges"')
    assert html.index('class="counts"') < html.index('class="fever"')
    assert "+12,949" in html
    assert "text-overflow:ellipsis" not in html
    assert "font-size:52px" in html
    assert "background:#ffcc00" in html
    assert "font-size:10.5px" not in html
    assert 'class="lbl"' in html
    assert "nth-child(odd)" not in html
    assert 'class="wordmark"' in html
    assert "data:image/png;base64," in html
    assert "/Users/" not in html
    assert html.index("wordmark") < html.index('class="final"')
    assert 'class="joke"' in html
    assert html.index('class="joke"') < html.index('class="counts"')
    assert "meta quiet" in html


def test_html_card_allowlist():
    recs = [prompt("SECRET-PROMPT-TEXT"),
            asst([tool_use("Bash", "t1", command="cat /Users/someone/secret/path.txt")]),
            result("t1", "SECRET-OUTPUT 5 passed")]
    s = analyze(write_fixture(recs))
    html = render_html(s, pick_buffs(s), score(s, pick_buffs(s)))
    for leak in ("SECRET-PROMPT-TEXT", "SECRET-OUTPUT", "secret/path", "/Users/"):
        assert leak not in html, f"card leaked: {leak}"


def test_score_floor():
    recs = [prompt()]
    for i in range(6):
        recs.append(asst([tool_use("Bash", f"e{i}", command="fail")]))
        recs.append(result(f"e{i}", "err", err=True))
    s = analyze(write_fixture(recs))
    core_buffs = [b for b in pick_buffs(s) if b[1] != "flavor"]  # tz-independent
    assert score(s, core_buffs) == 0
    # flavor may still add flat points on a floored core — comedy survives failure


def _min_s(**over):
    s = {"session_id": "x", "transcript_sha": "0" * 64, "models": {}, "efforts": {},
         "tools": {}, "green": 0, "red": 0, "longest_streak": 0, "worst_spiral": 0,
         "interruptions": 0, "compactions": 0, "first_tally": None, "last_tally": None,
         "first_ts": None, "last_ts": None, "user_prompts": 0, "tokens_in": 0,
         "tokens_out": 0, "yolo_mode": False, "plan_entries": 0, "overloads": 0,
         "longest_cook": 0, "night_events": 0, "worst_doom_loop": 0,
         "clean_window_chain": 0, "charm": False, "unknown_results": 0,
         "harness": "claude-code"}
    s.update(over)
    return s


def test_superlinear_streak():
    lo = score(_min_s(green=30, longest_streak=10), [])
    hi = score(_min_s(green=30, longest_streak=100), [])
    # 10x the streak must be worth far more than 10x the streak points
    assert hi - 300 == 1000 and lo - 300 == 31, (lo, hi)
    assert hi - 300 > 10 * (lo - 300)


def test_streak_cap():
    assert score(_min_s(longest_streak=100), []) == score(_min_s(longest_streak=5000), [])


def test_chain_product_cap():
    buffs = [(f"c{i}", "chain", 2.0, "") for i in range(5)]  # raw product 32
    assert score(_min_s(green=10), buffs) == int(100 * 6.0)  # capped at 6


def test_flavor_adds_never_multiplies():
    base = score(_min_s(green=10), [])
    with_flavor = score(_min_s(green=10), [("f", "flavor", 200, "")])
    assert with_flavor == base + 200
    # flavor on a zero-base session still shows up (comedy survives failure)
    assert score(_min_s(red=50), [("f", "flavor", 200, "")]) == 200


def test_debuff_bites_chains():
    buffs = [("c", "chain", 2.0, ""), ("d", "debuff", 0.5, "")]
    assert score(_min_s(green=10), buffs) == 100


def test_clean_window_chain_superlinear():
    s3 = score(_min_s(clean_window_chain=3), [])
    s9 = score(_min_s(clean_window_chain=9), [])
    # 3x the sustained chain must be worth much more than 3x the points
    assert s9 > 3 * s3, (s3, s9)


def test_clean_window_chain_from_transcript():
    recs = [prompt(ts="2026-08-19T10:00:00.000Z")]
    n = 0
    for w in range(3):          # 3 consecutive 20-min windows, 6 green events each
        for i in range(6):
            n += 1
            ts = f"2026-08-19T10:{w*20 + i*3:02d}:01.000Z"
            recs.append(asst([tool_use("Bash", f"w{n}", command=f"s{n}")], ts=ts))
            recs.append(result(f"w{n}", "ok", ts=ts))
    # sentinel in bucket 3 so buckets 0-2 are COMPLETED (in-progress bucket never counts)
    recs.append(asst([tool_use("Bash", "z9", command="done")], ts="2026-08-19T11:01:00.000Z"))
    recs.append(result("z9", "ok", ts="2026-08-19T11:01:00.000Z"))
    s = analyze(write_fixture(recs))
    assert s["clean_window_chain"] == 3, s["clean_window_chain"]
    assert "THE LONG GAME" in buff_names(s)


def test_in_progress_window_never_counts():
    # 6 clean events all inside the (still open) first bucket -> chain must be 0
    recs = [prompt(ts="2026-08-19T10:00:00.000Z")]
    for i in range(6):
        ts = f"2026-08-19T10:{i*3:02d}:01.000Z"
        recs.append(asst([tool_use("Bash", f"p{i}", command=f"s{i}")], ts=ts))
        recs.append(result(f"p{i}", "ok", ts=ts))
    s = analyze(write_fixture(recs))
    assert s["clean_window_chain"] == 0, s["clean_window_chain"]


def test_charm_requires_recovery():
    def spiral3(recover):
        recs = [prompt()]
        for i in range(3):
            recs.append(asst([tool_use("Bash", f"e{i}", command=f"x{i}")]))
            recs.append(result(f"e{i}", "err", err=True))
        if recover:
            recs.append(asst([tool_use("Bash", "ok", command="fix")]))
            recs.append(result("ok", "fine"))
        return analyze(write_fixture(recs))
    assert "Third Time's the Charm" in buff_names(spiral3(True))
    assert "Third Time's the Charm" not in buff_names(spiral3(False))


def test_tally_scoped_run_cannot_poison_delta():
    recs = [prompt(),
            asst([tool_use("Bash", "t1", command="pytest")]),
            result("t1", "500 passed, 0 failed"),
            asst([tool_use("Bash", "t2", command="pytest tests/test_one.py")]),
            result("t2", "1 passed, 0 failed"),
            asst([tool_use("Bash", "t3", command="pytest")]),
            result("t3", "512 passed, 0 failed")]
    s = analyze(write_fixture(recs))
    # delta comes from the repeated full-suite command, not the scoped run
    assert s["first_tally"] == (500, 0) and s["last_tally"] == (512, 0)


def test_window_chain_broken_by_error():
    recs = [prompt(ts="2026-08-19T10:00:00.000Z")]
    n = 0
    for w in range(3):
        for i in range(6):
            n += 1
            ts = f"2026-08-19T10:{w*20 + i*3:02d}:01.000Z"
            err = (w == 1 and i == 2)   # one error in the middle window
            recs.append(asst([tool_use("Bash", f"w{n}", command=f"s{n}")], ts=ts))
            recs.append(result(f"w{n}", "err" if err else "ok", err=err, ts=ts))
    s = analyze(write_fixture(recs))
    assert s["clean_window_chain"] == 1, s["clean_window_chain"]


def test_fingerprint_binds_transcript():
    recs = [prompt(), asst([tool_use("Bash", "t", command="ls")]), result("t", "ok")]
    a = analyze(write_fixture(recs))
    b = analyze(write_fixture(recs + [prompt("one more")]))
    assert a["transcript_sha"] != b["transcript_sha"]
    assert a["transcript_sha"][:12] in render_html(a, pick_buffs(a), 1)


def test_cook_resets_on_error():
    recs = [prompt()]
    for i in range(30):
        recs.append(asst([tool_use("Bash", f"a{i}", command=f"s{i}")]))
        recs.append(result(f"a{i}", "ok"))
    recs.append(asst([tool_use("Bash", "boom", command="x")]))
    recs.append(result("boom", "err", err=True))
    for i in range(20):
        recs.append(asst([tool_use("Bash", f"b{i}", command=f"t{i}")]))
        recs.append(result(f"b{i}", "ok"))
    s = analyze(write_fixture(recs))
    assert s["longest_cook"] == 30, s["longest_cook"]   # error broke the chain


def test_streak_chain_group_exclusive():
    # zero-error session: ONE-SHOT WONDER must suppress FLOW STATE/Clean Streak
    recs = [prompt()]
    for i in range(30):
        recs.append(asst([tool_use("Bash", f"g{i}", command=f"s{i}")]))
        recs.append(result(f"g{i}", "ok"))
    names = buff_names(analyze(write_fixture(recs)))
    assert "ONE-SHOT WONDER" in names
    assert "FLOW STATE" not in names and "Clean Streak" not in names


def test_sparse_windows_reset_chain():
    # clean window, then 2 empty windows, then clean window -> chain must be 1, not 2
    recs = [prompt(ts="2026-08-19T10:00:00.000Z")]
    n = 0
    for w in (0, 3):   # windows 1 and 2 are silent
        for i in range(6):
            n += 1
            ts = f"2026-08-19T{10 + (w*20 + i*3)//60}:{(w*20 + i*3) % 60:02d}:01.000Z"
            recs.append(asst([tool_use("Bash", f"w{n}", command=f"s{n}")], ts=ts))
            recs.append(result(f"w{n}", "ok", ts=ts))
    s = analyze(write_fixture(recs))
    assert s["clean_window_chain"] == 1, s["clean_window_chain"]


def test_meta_injection_sanitized():
    recs = [prompt(),
            asst([tool_use("Bash", "t", command="ls")],
                 model="claude-x<script>alert(1)</script>"),
            result("t", "ok")]
    s = analyze(write_fixture(recs))
    html = render_html(s, pick_buffs(s), 1)
    assert "<script>" not in html
    assert "claude-xscriptalert1script" in html  # stripped, not dropped


def test_badge_art_embedded_without_paths():
    """Badge art must travel as a data URI — never a filesystem reference."""
    from grade_session import badge_data_uri
    recs = [prompt()]
    for i in range(30):                     # earns a streak chain with art
        recs.append(asst([tool_use("Bash", f"g{i}", command=f"s{i}")]))
        recs.append(result(f"g{i}", "ok"))
    s = analyze(write_fixture(recs))
    buffs = pick_buffs(s)
    html = render_html(s, buffs, score(s, buffs))
    if badge_data_uri("ONE-SHOT WONDER"):   # assets present
        assert "data:image/png;base64," in html
        assert "assets/badges" not in html
        assert "/Users/" not in html


def _write(path, records):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def test_detect_and_grade_codex_fixture():
    from harness_adapters import detect_harness
    import tempfile, os
    d = tempfile.mkdtemp()
    p = os.path.join(d, "rollout-2026-08-20T10-00-00-01a00000-0000-7000-8000-000000000001.jsonl")
    recs = [
        {"timestamp": "2026-08-20T10:00:00.000Z", "type": "session_meta",
         "payload": {"session_id": "01a00000-0000-7000-8000-000000000001"}},
        {"timestamp": "2026-08-20T10:00:01.000Z", "type": "turn_context",
         "payload": {"model": "gpt-5.6-sol", "effort": "high",
                     "approval_policy": "never", "sandbox_policy": {"mode": "danger-full-access"}}},
        {"timestamp": "2026-08-20T10:00:02.000Z", "type": "event_msg",
         "payload": {"type": "user_message", "message": "go"}},
        {"timestamp": "2026-08-20T10:00:03.000Z", "type": "response_item",
         "payload": {"type": "function_call", "call_id": "c1", "name": "shell",
                     "arguments": "{}"}},
        {"timestamp": "2026-08-20T10:00:04.000Z", "type": "response_item",
         "payload": {"type": "function_call_output", "call_id": "c1",
                     "output": "done\nExit code: 0"}},
        {"timestamp": "2026-08-20T10:00:05.000Z", "type": "response_item",
         "payload": {"type": "custom_tool_call", "call_id": "c2", "name": "exec",
                     "input": "pytest -q"}},
        {"timestamp": "2026-08-20T10:00:06.000Z", "type": "response_item",
         "payload": {"type": "custom_tool_call_output", "call_id": "c2",
                     "output": [{"type": "input_text", "text": "no exit info"}]}},
        {"timestamp": "2026-08-20T10:00:07.000Z", "type": "compacted", "payload": {}},
        # cumulative snapshots: only the FINAL totals may be counted, and
        # input_tokens already includes cached tokens (no double add)
        {"timestamp": "2026-08-20T10:00:08.000Z", "type": "event_msg",
         "payload": {"type": "token_count", "info": {"total_token_usage": {
             "input_tokens": 500, "cached_input_tokens": 400, "output_tokens": 20}}}},
        {"timestamp": "2026-08-20T10:00:09.000Z", "type": "event_msg",
         "payload": {"type": "token_count", "info": {"total_token_usage": {
             "input_tokens": 1000, "cached_input_tokens": 900, "output_tokens": 50}}}},
        # current rollouts may carry user turns only as role-user messages
        {"timestamp": "2026-08-20T10:00:10.000Z", "type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "again"}]}},
    ]
    _write(p, recs)
    assert detect_harness(p) == "codex"
    s = analyze(p)
    assert s["harness"] == "codex"
    assert s["green"] == 1 and s["red"] == 0 and s["unknown_results"] == 1
    assert s["yolo_mode"] is True            # never + danger sandbox
    assert s["compactions"] == 1
    assert s["tokens_in"] == 1000 and s["tokens_out"] == 50   # final totals only
    assert s["efforts"] == {"high": 1}
    assert s["user_prompts"] == 2            # event_msg + role-user variants


def test_codex_function_call_command_extraction():
    from harness_adapters import _codex_command
    assert _codex_command({"input": "pytest -q"}) == "pytest -q"
    assert _codex_command({"arguments": json.dumps({"command": "make test"})}) == "make test"
    assert _codex_command({"arguments": json.dumps({"cmd": ["go", "test"]})}) == "go test"
    assert _codex_command({"arguments": "not json"}) is None
    assert _codex_command({}) is None


def test_gemini_running_status_does_not_lock_unknown():
    from harness_adapters import detect_harness
    import tempfile, os
    d = tempfile.mkdtemp()
    p = os.path.join(d, "session-2026-08-20T11-00-aaaa1111.jsonl")
    running = {"id": "g9", "name": "run_shell_command",
               "args": {"command": "ls"}, "status": "running"}
    done = dict(running, status="success", resultDisplay="ok")
    _write(p, [
        {"sessionId": "aaaa1111", "projectHash": "ff", "kind": "main"},
        {"id": "m1", "timestamp": "2026-08-20T11:00:01.000Z", "type": "gemini",
         "content": "", "toolCalls": [running]},
        {"id": "m1", "timestamp": "2026-08-20T11:00:02.000Z", "type": "gemini",
         "content": "", "toolCalls": [done]},
    ])
    s = analyze(p)
    assert s["green"] == 1 and s["unknown_results"] == 0, (s["green"], s["unknown_results"])


def test_unknown_results_never_fill_clean_windows():
    # five unknown-outcome results in a completed window must NOT make it clean
    recs = [prompt(ts="2026-08-19T10:00:00.000Z")]
    for i in range(6):
        ts = f"2026-08-19T10:{i*3:02d}:01.000Z"
        recs.append(asst([tool_use("Bash", f"u{i}", command=f"s{i}")], ts=ts))
        # claude adapter has no unknowns, so build the window via analyze on a
        # synthetic codex file instead
    import tempfile, os
    d = tempfile.mkdtemp()
    p = os.path.join(d, "rollout-2026-08-20T11-00-01a00000-0000-7000-8000-00000000000f.jsonl")
    rows = [{"timestamp": "2026-08-20T10:00:00.000Z", "type": "session_meta",
             "payload": {"session_id": "x"}}]
    for i in range(6):
        ts = f"2026-08-20T10:{i*3:02d}:01.000Z"
        rows.append({"timestamp": ts, "type": "response_item",
                     "payload": {"type": "custom_tool_call", "call_id": f"c{i}",
                                 "name": "exec", "input": f"s{i}"}})
        rows.append({"timestamp": ts, "type": "response_item",
                     "payload": {"type": "custom_tool_call_output", "call_id": f"c{i}",
                                 "output": "no exit info"}})   # unknown outcome
    rows.append({"timestamp": "2026-08-20T10:41:00.000Z", "type": "response_item",
                 "payload": {"type": "custom_tool_call", "call_id": "z",
                             "name": "exec", "input": "z"}})
    rows.append({"timestamp": "2026-08-20T10:41:01.000Z", "type": "response_item",
                 "payload": {"type": "custom_tool_call_output", "call_id": "z",
                             "output": "Exit code: 0"}})
    _write(p, rows)
    s = analyze(p)
    assert s["unknown_results"] == 6
    assert s["clean_window_chain"] == 0, s["clean_window_chain"]


def test_detect_and_grade_grok_fixture():
    from harness_adapters import detect_harness
    import tempfile, os
    d = tempfile.mkdtemp()
    sess = os.path.join(d, "019f0000-0000-7000-8000-000000000abc")
    os.makedirs(os.path.join(sess, "compaction_checkpoints"))
    open(os.path.join(sess, "compaction_checkpoints", "cp1"), "w").write("x")
    open(os.path.join(sess, "summary.json"), "w").write("{}")
    _write(os.path.join(sess, "events.jsonl"), [
        {"ts": "2026-08-20T10:00:00.000Z", "type": "turn_started",
         "session_id": "019f0000", "model_id": "grok-4.6", "yolo_mode": True,
         "session_relationship": "primary"},
        {"ts": "2026-08-20T10:00:01.000Z", "type": "tool_completed",
         "tool_name": "read_file", "outcome": "success", "tool_call_id": "t1"},
        {"ts": "2026-08-20T10:00:02.000Z", "type": "tool_completed",
         "tool_name": "shell", "outcome": "error", "tool_call_id": "t2"},
        {"ts": "2026-08-20T10:00:03.000Z", "type": "tool_completed",
         "tool_name": "shell", "outcome": "permission_rejected", "tool_call_id": "t3"},
    ])
    _write(os.path.join(sess, "updates.jsonl"), [
        {"sessionUpdate": "tool_call", "toolCallId": "t2",
         "rawInput": {"command": "true"}},
        {"sessionUpdate": "turn_completed",
         "usage": {"inputTokens": 10, "cachedReadTokens": 90, "outputTokens": 7,
                   "totalTokens": 17}},
        # later snapshot is cumulative; cached is already inside inputTokens
        {"sessionUpdate": "turn_completed",
         "usage": {"inputTokens": 1000, "cachedReadTokens": 200, "outputTokens": 50,
                   "totalTokens": 1050}},
    ])
    assert detect_harness(sess) == "grok"
    s = analyze(sess)
    assert s["harness"] == "grok"
    assert s["green"] == 1 and s["red"] == 1 and s["unknown_results"] == 1
    assert s["yolo_mode"] is True and s["compactions"] == 1
    assert s["tokens_in"] == 1000 and s["tokens_out"] == 50
    assert s["models"] == {"grok-4.6": 1}
    assert s["worst_doom_loop"] == 1   # command recovered from updates.jsonl


def test_detect_and_grade_gemini_fixture():
    from harness_adapters import detect_harness
    import tempfile, os
    d = tempfile.mkdtemp()
    p = os.path.join(d, "session-2026-08-20T10-00-abcd1234.jsonl")
    call = {"id": "g1", "name": "run_shell_command",
            "args": {"command": "ls"}, "status": "success",
            "resultDisplay": "ok"}
    _write(p, [
        {"sessionId": "abcd1234", "projectHash": "ff", "kind": "main",
         "startTime": "2026-08-20T10:00:00.000Z", "lastUpdated": "x"},
        {"id": "m1", "timestamp": "2026-08-20T10:00:01.000Z", "type": "user",
         "content": [{"text": "go"}]},
        {"id": "m2", "timestamp": "2026-08-20T10:00:02.000Z", "type": "gemini",
         "content": "", "model": "gemini-3.7-flash",
         "tokens": {"input": 5, "cached": 5, "output": 3},
         "toolCalls": [call]},
        # duplicate update of the same message must not double-count the call
        {"id": "m2", "timestamp": "2026-08-20T10:00:03.000Z", "type": "gemini",
         "content": "done", "model": "gemini-3.7-flash",
         "tokens": {"input": 5, "cached": 5, "output": 3},
         "toolCalls": [call]},
        {"$set": {"lastUpdated": "x"}},
    ])
    assert detect_harness(p) == "gemini"
    s = analyze(p)
    assert s["harness"] == "gemini"
    assert s["green"] == 1 and s["red"] == 0     # deduped despite the repeat
    assert s["models"] == {"gemini-3.7-flash": 2}
    assert s["tokens_in"] == 20 and s["tokens_out"] == 6


def test_unknown_results_touch_nothing():
    # a null-success result between greens must not break the streak
    from grade_session import analyze as _a
    recs = [prompt(),
            asst([tool_use("Bash", "a", command="x")]), result("a", "ok"),
            asst([tool_use("Bash", "b", command="y")]), result("b", "ok")]
    s = _min_s(green=2, longest_streak=2)
    base = score(s, [])
    s2 = _min_s(green=2, longest_streak=2, unknown_results=5)
    assert score(s2, []) == base   # unknowns carry no points either way


def test_cli_smoke():
    recs = [prompt(), asst([tool_use("Bash", "t", command="ls")]), result("t", "ok")]
    fix = write_fixture(recs)
    out = subprocess.run([sys.executable, str(Path(__file__).parent / "grade_session.py"), fix],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "TERMINALLY COOKED" in out.stdout


def _grok_sess(home, sid, n_green, start, minutes, mtime):
    """Tiny Grok session dir. start is timezone-aware; mtime is epoch seconds."""
    import os
    d = Path(home) / ".grok" / "sessions" / "proj" / sid
    d.mkdir(parents=True)
    (d / "summary.json").write_text("{}")
    recs = []
    for i in range(n_green):
        ts = (start.timestamp() + i * 30)
        iso = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        recs.append({"ts": iso, "type": "turn_started", "model_id": "grok-4.6",
                     "yolo_mode": False})
        recs.append({"ts": iso, "type": "tool_completed", "tool_name": "read_file",
                     "outcome": "success", "tool_call_id": f"t{i}"})
    # stretch last timestamp to requested duration
    end = start.timestamp() + minutes * 60
    recs[-1]["ts"] = datetime.fromtimestamp(end, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z")
    _write(d / "events.jsonl", recs)
    os.utime(d / "events.jsonl", (mtime, mtime))
    os.utime(d / "summary.json", (mtime, mtime))
    return d


def test_pick_skips_live_even_when_live_is_juicier():
    from datetime import timedelta
    from grade_session import pick_juicy_session
    home = Path(tempfile.mkdtemp())
    now = datetime.now(timezone.utc)
    today = now.replace(hour=12, minute=0, second=0, microsecond=0)
    live = _grok_sess(home, "live0000-0000-7000-8000-000000000001",
                      n_green=80, start=today, minutes=40, mtime=now.timestamp())
    alt = _grok_sess(home, "alt00000-0000-7000-8000-000000000002",
                     n_green=20, start=today - timedelta(minutes=90),
                     minutes=30, mtime=now.timestamp() - 3600)
    picked, note = pick_juicy_session(home=home, now=now, live_ids=[])
    assert picked.resolve() == alt.resolve(), (picked, note)
    assert "live" in note and "alt00000" in note


def test_pick_falls_back_when_today_is_only_live():
    from datetime import timedelta
    from grade_session import pick_juicy_session
    home = Path(tempfile.mkdtemp())
    now = datetime.now(timezone.utc)
    today = now.replace(hour=12, minute=0, second=0, microsecond=0)
    last_week = today - timedelta(days=6)
    live = _grok_sess(home, "live0000-0000-7000-8000-000000000001",
                      n_green=3, start=today, minutes=5, mtime=now.timestamp())
    old = _grok_sess(home, "old00000-0000-7000-8000-000000000003",
                     n_green=40, start=last_week, minutes=50,
                     mtime=(last_week).timestamp())
    picked, note = pick_juicy_session(home=home, now=now, live_ids=[])
    assert picked.resolve() == old.resolve(), (picked, note)


def test_pick_prefers_longer_session_over_one_minute_blitz():
    from datetime import timedelta
    from grade_session import pick_juicy_session
    home = Path(tempfile.mkdtemp())
    now = datetime.now(timezone.utc)
    today = now.replace(hour=12, minute=0, second=0, microsecond=0)
    live = _grok_sess(home, "live0000-0000-7000-8000-000000000001",
                      n_green=2, start=today, minutes=2, mtime=now.timestamp())
    blitz = _grok_sess(home, "blitz000-0000-7000-8000-000000000004",
                       n_green=12, start=today - timedelta(minutes=10),
                       minutes=1, mtime=now.timestamp() - 600)
    haul = _grok_sess(home, "haul0000-0000-7000-8000-000000000005",
                      n_green=12, start=today - timedelta(hours=3),
                      minutes=40, mtime=now.timestamp() - 7200)
    picked, note = pick_juicy_session(home=home, now=now, live_ids=[])
    assert picked.resolve() == haul.resolve(), (picked, note)


def test_claude_slug_encodes_underscore():
    from grade_session import claude_project_slug
    cwd = "/private/var/folders/9_/tmp/air-claude-code-p04jm_wu"
    assert claude_project_slug(cwd) == (
        "-private-var-folders-9--tmp-air-claude-code-p04jm-wu")


def test_juice_counts_unknowns_and_rejects_probes():
    from grade_session import juice_score
    work = _min_s(green=0, red=0, unknown_results=40,
                  first_ts="2026-08-20T10:00:00.000Z",
                  last_ts="2026-08-20T10:30:00.000Z")
    probe = _min_s(green=80, red=0, unknown_results=0,
                   first_ts="2026-08-20T10:00:00.000Z",
                   last_ts="2026-08-20T10:01:00.000Z")
    assert juice_score(work) > juice_score(probe)
    assert juice_score(work) == 40


def test_pick_rejects_high_volume_one_minute_blitz():
    from datetime import timedelta
    from grade_session import pick_juicy_session
    home = Path(tempfile.mkdtemp())
    now = datetime.now(timezone.utc)
    today = now.replace(hour=12, minute=0, second=0, microsecond=0)
    live = _grok_sess(home, "live0000-0000-7000-8000-000000000001",
                      n_green=2, start=today, minutes=2, mtime=now.timestamp())
    blitz = _grok_sess(home, "blitz000-0000-7000-8000-00000000000c",
                       n_green=80, start=today - timedelta(minutes=10),
                       minutes=1, mtime=now.timestamp() - 600)
    haul = _grok_sess(home, "haul0000-0000-7000-8000-00000000000d",
                      n_green=14, start=today - timedelta(hours=2),
                      minutes=30, mtime=now.timestamp() - 7200)
    picked, note = pick_juicy_session(home=home, now=now, live_ids=[])
    assert picked.resolve() == haul.resolve(), (picked, note)


def test_pick_claude_cwd_skips_newest_in_project():
    import os
    from grade_session import pick_juicy_session, claude_project_slug
    home = Path(tempfile.mkdtemp())
    cwd = Path("/Users/example/projects/Game Dev")
    slug = claude_project_slug(cwd)
    d = Path(home) / ".claude" / "projects" / slug
    d.mkdir(parents=True)
    now = datetime.now(timezone.utc).timestamp()
    # Auto-pick only looks back a week, so session timestamps must be recent.
    day = datetime.now().date().isoformat()

    def claude_jsonl(name, n_green, mtime):
        recs = [prompt(ts=f"{day}T10:00:00.000Z")]
        for i in range(n_green):
            recs.append(asst([tool_use("Bash", f"t{i}", command="ls")],
                             ts=f"{day}T10:{i:02d}:00.000Z"))
            recs.append(result(f"t{i}", "ok", ts=f"{day}T10:{i:02d}:05.000Z"))
        recs[-1]["timestamp"] = f"{day}T10:40:00.000Z"
        p = d / name
        _write(p, recs)
        os.utime(p, (mtime, mtime))
        return p

    live = claude_jsonl("aaaaaaaa-1111-4000-8000-000000000001.jsonl", 8, now)
    other = claude_jsonl("bbbbbbbb-2222-4000-8000-000000000002.jsonl", 20, now - 3600)
    picked, note = pick_juicy_session(
        home=home, live_ids=[], env={}, cwd=cwd)
    assert picked.resolve() == other.resolve(), (picked, note)
    assert "aaaaaaaa" in note


def test_pick_prefers_yesterdays_work_over_todays_probe():
    from datetime import timedelta
    from grade_session import pick_juicy_session
    home = Path(tempfile.mkdtemp())
    now = datetime.now(timezone.utc)
    today = now.replace(hour=12, minute=0, second=0, microsecond=0)
    live = _grok_sess(home, "live0000-0000-7000-8000-000000000001",
                      n_green=2, start=today, minutes=2, mtime=now.timestamp())
    probe = _grok_sess(home, "probe000-0000-7000-8000-00000000000e",
                       n_green=80, start=today - timedelta(hours=1),
                       minutes=1, mtime=now.timestamp() - 3600)
    haul = _grok_sess(home, "haul0000-0000-7000-8000-00000000000f",
                      n_green=14, start=today - timedelta(days=1),
                      minutes=30, mtime=now.timestamp() - 86400)
    picked, note = pick_juicy_session(home=home, now=now, live_ids=[])
    assert picked.resolve() == haul.resolve(), (picked, note)


def test_grok_hash_is_boundary_safe():
    from grade_session import analyze, pick_buffs, score
    home = Path(tempfile.mkdtemp())
    now = datetime.now(timezone.utc)
    a = _grok_sess(home, "bound000-0000-7000-8000-000000000010",
                   n_green=1, start=now, minutes=5, mtime=now.timestamp())
    bdir = Path(home) / ".grok" / "sessions" / "proj" / "bound001-0000-7000-8000-000000000011"
    bdir.mkdir(parents=True)
    (bdir / "summary.json").write_text("{}")
    # same bytes split across the two files must not hash equal
    ev = (a / "events.jsonl").read_text()
    (a / "updates.jsonl").write_text("")
    (bdir / "events.jsonl").write_text("")
    (bdir / "updates.jsonl").write_text(ev)
    sa, sb = analyze(a), analyze(bdir)
    assert sa["transcript_sha"] != sb["transcript_sha"]


def test_pick_skips_invoker_even_when_not_newest():
    """The live session is identified by id, not by being the newest file."""
    from datetime import timedelta
    from grade_session import pick_juicy_session
    home = Path(tempfile.mkdtemp())
    now = datetime.now(timezone.utc)
    today = now.replace(hour=12, minute=0, second=0, microsecond=0)
    other = _grok_sess(home, "other000-0000-7000-8000-000000000006",
                       n_green=20, start=today, minutes=30, mtime=now.timestamp())
    invoker = _grok_sess(home, "invoke00-0000-7000-8000-000000000007",
                         n_green=80, start=today - timedelta(minutes=20),
                         minutes=40, mtime=now.timestamp() - 60)
    picked, note = pick_juicy_session(
        home=home, now=now, live_ids=["invoke00-0000-7000-8000-000000000007"])
    assert picked.resolve() == other.resolve(), (picked, note)
    assert "invoke00" in note


def test_grok_session_mtime_uses_newest_file():
    import os
    from harness_adapters import session_mtime
    home = Path(tempfile.mkdtemp())
    now = datetime.now(timezone.utc)
    d = _grok_sess(home, "mtime000-0000-7000-8000-000000000008",
                   n_green=2, start=now, minutes=5, mtime=1000)
    (d / "updates.jsonl").write_text("{}\n")
    os.utime(d / "events.jsonl", (1000, 1000))
    os.utime(d / "updates.jsonl", (5000, 5000))
    assert session_mtime(d) == 5000


def test_grok_fingerprint_includes_updates():
    from grade_session import analyze
    home = Path(tempfile.mkdtemp())
    now = datetime.now(timezone.utc)
    d = _grok_sess(home, "hash0000-0000-7000-8000-000000000009",
                   n_green=2, start=now, minutes=5, mtime=now.timestamp())
    (d / "updates.jsonl").write_text(
        json.dumps({"sessionUpdate": "turn_completed",
                    "usage": {"inputTokens": 10, "outputTokens": 1}}) + "\n")
    a = analyze(d)
    (d / "updates.jsonl").write_text(
        json.dumps({"sessionUpdate": "turn_completed",
                    "usage": {"inputTokens": 99, "outputTokens": 1}}) + "\n")
    b = analyze(d)
    assert a["tokens_in"] != b["tokens_in"]
    assert a["transcript_sha"] != b["transcript_sha"]


def test_list_sessions_skips_codex_subagents():
    import os
    from harness_adapters import list_sessions
    home = Path(tempfile.mkdtemp())
    d = Path(home) / ".codex" / "sessions" / "2026" / "08" / "20"
    d.mkdir(parents=True)
    sid_main = "01a00000-0000-7000-8000-00000000000a"
    sid_sub = "01a00000-0000-7000-8000-00000000000b"
    main = d / f"rollout-2026-08-20T10-00-00-{sid_main}.jsonl"
    sub = d / f"rollout-2026-08-20T10-00-01-{sid_sub}.jsonl"
    _write(main, [
        {"timestamp": "2026-08-20T10:00:00.000Z", "type": "session_meta",
         "payload": {"session_id": sid_main, "source": "cli"}},
    ])
    _write(sub, [
        {"timestamp": "2026-08-20T10:00:01.000Z", "type": "session_meta",
         "payload": {"session_id": sid_sub, "source": {"subagent": {"thread_spawn": {}}},
                     "parent_thread_id": sid_main}},
    ])
    found = list_sessions(home)
    names = {p.name for p in found}
    assert main.name in names
    assert sub.name not in names


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted({k: v for k, v in globals().items() if k.startswith("test_")}.items()):
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as e:
            fails += 1
            print(f"FAIL {name}: {e}")
    print(f"\n{'FAILED' if fails else 'OK'} — {fails} failures")
    sys.exit(1 if fails else 0)
