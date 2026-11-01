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
    assert "<script>" not in html and "alert" not in html
    assert "other model" in html  # not a vendor id shape: neutral label, never the text


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
                     "output": "Exit code: 0\nWall time: 0.1 seconds\nOutput:\ndone"}},
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
    assert s["user_prompts"] == 1            # event_msg stream wins over role-user items


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
        # a repeat of the same message is a snapshot: call, model and tokens count once
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
    assert s["models"] == {"gemini-3.7-flash": 1}
    assert s["tokens_in"] == 10 and s["tokens_out"] == 3


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
    step = min(30, minutes * 60 / max(n_green, 1))   # events stay inside the duration
    for i in range(n_green):
        ts = (start.timestamp() + i * step)
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
    live = _grok_sess(home, "11fe0000-0000-7000-8000-000000000001",
                      n_green=80, start=today, minutes=40, mtime=now.timestamp())
    alt = _grok_sess(home, "a1700000-0000-7000-8000-000000000002",
                     n_green=20, start=today - timedelta(minutes=90),
                     minutes=30, mtime=now.timestamp() - 3600)
    picked, note = pick_juicy_session(home=home, now=now, live_ids=[])
    assert picked.resolve() == alt.resolve(), (picked, note)
    assert "live" in note and "a1700000" in note


def test_pick_falls_back_when_today_is_only_live():
    from datetime import timedelta
    from grade_session import pick_juicy_session
    home = Path(tempfile.mkdtemp())
    now = datetime.now(timezone.utc)
    today = now.replace(hour=12, minute=0, second=0, microsecond=0)
    last_week = today - timedelta(days=6)
    live = _grok_sess(home, "11fe0000-0000-7000-8000-000000000001",
                      n_green=3, start=today, minutes=5, mtime=now.timestamp())
    old = _grok_sess(home, "01d00000-0000-7000-8000-000000000003",
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
    live = _grok_sess(home, "11fe0000-0000-7000-8000-000000000001",
                      n_green=2, start=today, minutes=2, mtime=now.timestamp())
    blitz = _grok_sess(home, "b1172000-0000-7000-8000-000000000004",
                       n_green=12, start=today - timedelta(minutes=10),
                       minutes=1, mtime=now.timestamp() - 600)
    haul = _grok_sess(home, "aa010000-0000-7000-8000-000000000005",
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
    live = _grok_sess(home, "11fe0000-0000-7000-8000-000000000001",
                      n_green=2, start=today, minutes=2, mtime=now.timestamp())
    blitz = _grok_sess(home, "b1172000-0000-7000-8000-00000000000c",
                       n_green=80, start=today - timedelta(minutes=10),
                       minutes=1, mtime=now.timestamp() - 600)
    haul = _grok_sess(home, "aa010000-0000-7000-8000-00000000000d",
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
    live = _grok_sess(home, "11fe0000-0000-7000-8000-000000000001",
                      n_green=2, start=today, minutes=2, mtime=now.timestamp())
    probe = _grok_sess(home, "b10be000-0000-7000-8000-00000000000e",
                       n_green=80, start=today - timedelta(hours=1),
                       minutes=1, mtime=now.timestamp() - 3600)
    haul = _grok_sess(home, "aa010000-0000-7000-8000-00000000000f",
                      n_green=14, start=today - timedelta(days=1),
                      minutes=30, mtime=now.timestamp() - 86400)
    picked, note = pick_juicy_session(home=home, now=now, live_ids=[])
    assert picked.resolve() == haul.resolve(), (picked, note)


def test_grok_hash_is_boundary_safe():
    from grade_session import analyze, pick_buffs, score
    home = Path(tempfile.mkdtemp())
    now = datetime.now(timezone.utc)
    a = _grok_sess(home, "b0a00000-0000-7000-8000-000000000010",
                   n_green=1, start=now, minutes=5, mtime=now.timestamp())
    bdir = Path(home) / ".grok" / "sessions" / "proj" / "b0a00001-0000-7000-8000-000000000011"
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
    other = _grok_sess(home, "07e40000-0000-7000-8000-000000000006",
                       n_green=20, start=today, minutes=30, mtime=now.timestamp())
    invoker = _grok_sess(home, "1a40ce00-0000-7000-8000-000000000007",
                         n_green=80, start=today - timedelta(minutes=20),
                         minutes=40, mtime=now.timestamp() - 60)
    picked, note = pick_juicy_session(
        home=home, now=now, live_ids=["1a40ce00-0000-7000-8000-000000000007"])
    assert picked.resolve() == other.resolve(), (picked, note)
    assert "1a40ce00" in note


def test_grok_session_mtime_uses_newest_file():
    import os
    from harness_adapters import session_mtime
    home = Path(tempfile.mkdtemp())
    now = datetime.now(timezone.utc)
    d = _grok_sess(home, "e7100000-0000-7000-8000-000000000008",
                   n_green=2, start=now, minutes=5, mtime=1000)
    (d / "updates.jsonl").write_text("{}\n")
    os.utime(d / "events.jsonl", (1000, 1000))
    os.utime(d / "updates.jsonl", (5000, 5000))
    assert session_mtime(d) == 5000


def test_grok_fingerprint_includes_updates():
    from grade_session import analyze
    home = Path(tempfile.mkdtemp())
    now = datetime.now(timezone.utc)
    d = _grok_sess(home, "aa5a0000-0000-7000-8000-000000000009",
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


# ---------------------------------------------------------------- v0.6 review fixes

import grade_session as gs

GS_PATH = Path(__file__).parent / "grade_session.py"
UUID_A = "0a1b2c3d-1111-4000-8000-00000000000a"
LEAKS = ("SECRET42", "secret42", "alice", "acme", "private-repo", "<script", "\x1b[2J", "\x1b]2;", "\x07")


def _cli(args, cwd, env_extra=None):
    env = os.environ.copy()
    for k in gs.INVOKER_ENV:
        env.pop(k, None)
    env["TERMINALLY_COOKED_NO_OPEN"] = "1"
    env.update(env_extra or {})
    return subprocess.run([sys.executable, str(GS_PATH)] + [str(a) for a in args],
                          capture_output=True, text=True, env=env, cwd=str(cwd))


def _adversarial_claude(d, name="SECRET42-client.jsonl"):
    recs = [prompt("SECRET42 prompt", ts="2026-08-19T10:00:00.000Z")]
    names = ["/Users/alice/private-repo", "mcp__acme-secret__deploy", "Bash\x1b[2J\x1b]2;pwned\x07",
             "<script>alert(1)</script>", "Bash"]
    for i, n in enumerate(names):
        recs.append(asst([tool_use(n, f"a{i}", command="ls")],
                         model="gpt\x1b]2;pwned\x07-x", ts=f"2026-08-19T10:0{i}:00.000Z"))
        recs.append(result(f"a{i}", "ok", ts=f"2026-08-19T10:0{i}:30.000Z"))
    p = Path(d) / name
    _write(p, recs)
    return p


def test_card_id_never_from_arbitrary_filename():
    d = Path(tempfile.mkdtemp())
    p = _adversarial_claude(d)
    s = analyze(p)
    assert s["session_id"] == s["transcript_sha"][:8], s["session_id"]
    buffs = pick_buffs(s)
    out = gs.render(s, buffs, 1) + gs.render_html(s, buffs, 1) + gs.share_caption(s, buffs, 1)
    for leak in LEAKS:
        assert leak not in out, f"card leaked {leak!r}"


def test_session_label_shapes():
    from harness_adapters import session_label
    d = Path(tempfile.mkdtemp())
    assert session_label(d / f"{UUID_A}.jsonl") == UUID_A
    assert session_label(d / f"rollout-2026-08-20T10-00-00-{UUID_A}.jsonl") == UUID_A
    assert session_label(d / "session-2026-08-20T10-00-abcd1234.jsonl") == "abcd1234"
    g = d / UUID_A
    g.mkdir()
    assert session_label(g) == UUID_A
    assert session_label(d / "SECRET42-client.jsonl") is None
    assert session_label(d / "rollout-acme-payroll.jsonl") is None
    cwd = os.getcwd()
    try:
        os.chdir(g)
        assert session_label(Path(".")) == UUID_A
    finally:
        os.chdir(cwd)


def test_gemini_card_id_and_prefix_lookup():
    from grade_session import find_session
    home = Path(tempfile.mkdtemp())
    chats = home / ".gemini" / "tmp" / "ffff" / "chats"
    chats.mkdir(parents=True)
    p = chats / "session-2026-08-20T10-00-abcd1234.jsonl"
    _write(p, [{"sessionId": "abcd1234-0000-4000-8000-000000000000", "projectHash": "ff"},
               {"id": "m1", "timestamp": "2026-08-20T10:00:01.000Z", "type": "user",
                "content": [{"text": "go"}]}])
    assert analyze(p)["session_id"] == "abcd1234"
    found, _ = find_session("abcd1234", home=home, env={})
    assert found.resolve() == p.resolve()
    found, _ = find_session("abcd1234-0000-4000-8000-000000000000", home=home, env={})
    assert found.resolve() == p.resolve()


def test_tool_names_allowlisted():
    d = Path(tempfile.mkdtemp())
    s = analyze(_adversarial_claude(d, f"{UUID_A}.jsonl"))
    assert set(s["tools"]) <= {"Bash", "MCP", "Other"}, s["tools"]
    assert s["tools"]["Bash"] == 1 and s["tools"]["MCP"] == 1 and s["tools"]["Other"] == 3


def test_adversarial_cli_render_paths():
    d = Path(tempfile.mkdtemp())
    p = _adversarial_claude(d)
    work = Path(tempfile.mkdtemp())
    out = _cli([p, "--html"], work, {"FORCE_COLOR": "1"})
    assert out.returncode == 0, out.stderr
    for leak in LEAKS:
        assert leak not in out.stdout and leak not in out.stderr, f"terminal leaked {leak!r}"
    files = list(work.iterdir())
    assert len(files) == 1, files
    assert "SECRET42" not in files[0].name and "secret42" not in files[0].name.lower()
    html = files[0].read_text()
    for leak in LEAKS:
        assert leak not in html, f"html leaked {leak!r}"


def test_untrusted_timestamp_never_renders():
    d = Path(tempfile.mkdtemp())
    p = d / f"{UUID_A}.jsonl"
    _write(p, [prompt(ts="\x1b[2J<b>2026-08-19T10:00:00Z"),
               asst([tool_use("Bash", "t", command="ls")]), result("t", "ok")])
    s = analyze(p)
    out = gs.render(s, pick_buffs(s), 1) + gs.render_html(s, pick_buffs(s), 1)
    assert "\x1b[2J" not in out and "<b>" not in out


def _claude_home_session(home, slug, sid, n_green, mtime, day=None, pad=0):
    day = day or datetime.now().date().isoformat()
    d = Path(home) / ".claude" / "projects" / slug
    d.mkdir(parents=True, exist_ok=True)
    recs = [prompt(ts=f"{day}T10:00:00.000Z")]
    for i in range(n_green):
        recs.append(asst([tool_use("Bash", f"t{i}", command="ls")], ts=f"{day}T10:{i:02d}:00.000Z"))
        recs.append(result(f"t{i}", "ok" + "x" * pad, ts=f"{day}T10:{i:02d}:05.000Z"))
    recs[-1]["timestamp"] = f"{day}T10:40:00.000Z"
    p = d / f"{sid}.jsonl"
    _write(p, recs)
    os.utime(p, (mtime, mtime))
    return p


def test_live_exclusion_runs_before_size_cap():
    home = Path(tempfile.mkdtemp())
    cwd = Path("/Users/example/projects/sizecap")
    slug = gs.claude_project_slug(cwd)
    now = datetime.now(timezone.utc).timestamp()
    live = _claude_home_session(home, slug, "aaaaaaaa-1111-4000-8000-000000000001", 30, now, pad=4000)
    work = _claude_home_session(home, slug, "bbbbbbbb-2222-4000-8000-000000000002", 20, now - 3600)
    saved = gs.MAX_PICK_BYTES
    gs.MAX_PICK_BYTES = 20_000
    try:
        picked, note = gs.pick_juicy_session(home=home, live_ids=[], env={}, cwd=cwd)
    finally:
        gs.MAX_PICK_BYTES = saved
    assert picked is not None and picked.resolve() == work.resolve(), (picked, note)


def test_stale_same_cwd_claude_does_not_shield_live_session():
    from datetime import timedelta
    home = Path(tempfile.mkdtemp())
    cwd = Path("/Users/example/projects/stale")
    slug = gs.claude_project_slug(cwd)
    now = datetime.now(timezone.utc)
    today = now.replace(hour=12, minute=0, second=0, microsecond=0)
    week = (now - timedelta(days=6)).date().isoformat()
    _claude_home_session(home, slug, "cccccccc-3333-4000-8000-000000000003", 5,
                         now.timestamp() - 6 * 86400, day=week)
    live = _grok_sess(home, "11fe0000-0000-7000-8000-000000000001",
                      n_green=80, start=today, minutes=40, mtime=now.timestamp())
    other = _grok_sess(home, "07e40000-0000-7000-8000-000000000006",
                       n_green=20, start=today - timedelta(hours=2), minutes=30,
                       mtime=now.timestamp() - 3600)
    picked, note = gs.pick_juicy_session(home=home, now=now, live_ids=[], env={}, cwd=cwd)
    assert picked is not None and picked.resolve() == other.resolve(), (picked, note)
    assert "heuristic" in note, note


def test_unknown_invoker_excludes_newest_per_harness():
    from datetime import timedelta
    home = Path(tempfile.mkdtemp())
    now = datetime.now(timezone.utc)
    today = now.replace(hour=12, minute=0, second=0, microsecond=0)
    live = _grok_sess(home, "11fe0000-0000-7000-8000-000000000001",
                      n_green=80, start=today - timedelta(hours=1), minutes=40,
                      mtime=now.timestamp() - 600)
    cdx = Path(home) / ".codex" / "sessions" / "2026" / "08" / "20"
    cdx.mkdir(parents=True)
    newer = cdx / f"rollout-2026-08-20T10-00-00-{UUID_A}.jsonl"
    _write(newer, [{"timestamp": "2026-08-20T10:00:00.000Z", "type": "session_meta",
                    "payload": {"session_id": UUID_A}}])
    picked, note = gs.pick_juicy_session(home=home, now=now, live_ids=[], env={},
                                         cwd=Path("/nowhere"))
    assert picked is None or picked.resolve() != live.resolve(), (picked, note)
    assert "heuristic" in note, note


def test_recognized_invoker_skips_only_that_session():
    from datetime import timedelta
    home = Path(tempfile.mkdtemp())
    cwd = Path("/Users/example/projects/known")
    slug = gs.claude_project_slug(cwd)
    now = datetime.now(timezone.utc)
    work = _claude_home_session(home, slug, "dddddddd-4444-4000-8000-000000000004", 30,
                                now.timestamp())
    inv = "1a40ce00-0000-7000-8000-000000000007"
    _grok_sess(home, inv, n_green=5, start=now - timedelta(minutes=30), minutes=20,
               mtime=now.timestamp() - 60)
    picked, note = gs.pick_juicy_session(home=home, now=now, live_ids=[inv], env={}, cwd=cwd)
    assert picked is not None and picked.resolve() == work.resolve(), (picked, note)
    assert "heuristic" not in note


def test_explicit_target_matching_invoker_is_refused():
    from grade_session import find_session
    home = Path(tempfile.mkdtemp())
    now = datetime.now(timezone.utc)
    inv = "1a40ce00-0000-7000-8000-000000000007"
    d = _grok_sess(home, inv, n_green=3, start=now, minutes=5, mtime=now.timestamp())
    for arg in (str(d), "1a40ce00"):
        try:
            find_session(arg, home=home, env={"GROK_SESSION_ID": inv})
        except SystemExit as e:
            assert "invoking" in str(e.code), e.code
        else:
            raise AssertionError(f"graded the invoking session via {arg}")


def _fake_chrome(d, body):
    script = Path(d) / "fakechrome"
    script.write_text("#!/bin/sh\n"
                      'for a in "$@"; do echo "$a" >> "$FAKE_LOG";\n'
                      '  case "$a" in --screenshot=*) out="${a#--screenshot=}";; esac; done\n'
                      + body)
    script.chmod(0o755)
    return script


def _card_png(path):
    rows = [[(255, 0, 255)] * 120 for _ in range(120)]
    for y in range(10, 110):
        for x in range(10, 110):
            rows[y][x] = ((x * 37 + y * 11) % 200, 204, (x * y) % 50)
    gs.write_png_rgb(path, rows)
    assert Path(path).stat().st_size > 400


def test_png_renderer_network_off_and_csp():
    d = Path(tempfile.mkdtemp())
    src = d / "good.png"
    _card_png(src)
    chrome = _fake_chrome(d, f'cp "{src}" "$out"\n')
    sess = Path(tempfile.mkdtemp()) / f"{UUID_A}.jsonl"
    _write(sess, [prompt(), asst([tool_use("Bash", "t", command="ls")]), result("t", "ok")])
    work = Path(tempfile.mkdtemp())
    log = d / "argv.log"
    out = _cli([sess, "--png", "card.png"], work, {"CHROME_BIN": str(chrome), "FAKE_LOG": str(log)})
    assert out.returncode == 0, out.stderr
    argv = log.read_text().splitlines()
    for flag in ("--disable-background-networking", "--disable-component-update", "--disable-sync",
                 "--disable-default-apps", "--disable-domain-reliability", "--no-pings",
                 "--host-resolver-rules=MAP * ~NOTFOUND"):
        assert flag in argv, f"missing {flag}"
    assert (work / "card.png").exists()
    csp = "default-src 'none'; img-src data:; style-src 'unsafe-inline'"
    html = list(work.glob("terminally-cooked-card-*.html"))
    assert len(html) == 1 and csp in html[0].read_text(), html
    assert csp in gs.html_page_for_png("<div></div>")


def test_png_waits_for_chrome_to_finish_writing():
    d = Path(tempfile.mkdtemp())
    src = d / "good.png"
    _card_png(src)
    chrome = _fake_chrome(d, f'head -c 150 "{src}" > "$out"; sleep 1; cp "{src}" "$out"\n')
    sess = Path(tempfile.mkdtemp()) / f"{UUID_A}.jsonl"
    _write(sess, [prompt(), asst([tool_use("Bash", "t", command="ls")]), result("t", "ok")])
    work = Path(tempfile.mkdtemp())
    out = _cli([sess, "--png", "card.png"], work,
               {"CHROME_BIN": str(chrome), "FAKE_LOG": str(d / "log")})
    assert out.returncode == 0, out.stderr
    assert (work / "card.png").exists(), out.stderr
    assert gs.read_png_rgb(work / "card.png")


def test_png_truncated_is_clean_error():
    d = Path(tempfile.mkdtemp())
    src = d / "good.png"
    _card_png(src)
    chrome = _fake_chrome(d, f'head -c 150 "{src}" > "$out"\n')
    sess = Path(tempfile.mkdtemp()) / f"{UUID_A}.jsonl"
    _write(sess, [prompt(), asst([tool_use("Bash", "t", command="ls")]), result("t", "ok")])
    work = Path(tempfile.mkdtemp())
    out = _cli([sess, "--png", "card.png"], work,
               {"CHROME_BIN": str(chrome), "FAKE_LOG": str(d / "log")})
    assert "Traceback" not in out.stderr, out.stderr
    assert "png card failed" in out.stderr, out.stderr
    assert not (work / "card.png").exists()


def test_read_png_corrupt_raises_value_error():
    d = Path(tempfile.mkdtemp())
    good = d / "g.png"
    _card_png(good)
    data = good.read_bytes()
    for name, blob in (("trunc", data[:len(data) // 2]),
                       ("badzlib", data[:41] + b"\x00" * 20 + data[61:])):
        p = d / f"{name}.png"
        p.write_bytes(blob)
        try:
            gs.crop_png_chroma(p, d / "out.png")
        except ValueError:
            pass
        else:
            raise AssertionError(f"{name} PNG did not raise ValueError")


def _tally_session(outputs, cmd="pytest"):
    recs = [prompt()]
    for i, text in enumerate(outputs):
        c = cmd[i] if isinstance(cmd, list) else cmd
        recs.append(asst([tool_use("Bash", f"t{i}", command=c)]))
        recs.append(result(f"t{i}", text))
    return analyze(write_fixture(recs))


def test_tally_counts_parsed_independently():
    s = _tally_session(["=== 3 failed, 12 passed in 0.42s ===", "=== 5 failed, 12 passed in 0.4s ==="])
    assert s["first_tally"] == (12, 3) and s["last_tally"] == (12, 5), (s["first_tally"], s["last_tally"])
    assert "Red Wedding" in buff_names(s)
    s = _tally_session(["Test Suites: 1 failed, 3 passed, 4 total\nTests:       2 failed, 10 passed, 12 total\nSnapshots:   0 total"] * 2,
                       cmd="npx jest")
    assert s["last_tally"] == (10, 2), s["last_tally"]
    s = _tally_session(["test result: FAILED. 12 passed; 3 failed; 0 ignored"] * 2, cmd="cargo test")
    assert s["last_tally"] == (12, 3), s["last_tally"]
    s = _tally_session(["=== 2 failed in 0.10s ===", "0 passed, 4 failed"])
    assert s["first_tally"] == (0, 2) and s["last_tally"] == (0, 4), (s["first_tally"], s["last_tally"])
    s = _tally_session(["12 passed, 3 failed", "15 passed, 0 failed"])
    assert s["first_tally"] == (12, 3) and s["last_tally"] == (15, 0)


def test_tally_ties_break_by_suite_size():
    s = _tally_session(["1 passed", "1 passed", "500 passed", "512 passed"],
                       cmd=["pytest tests/test_one.py", "pytest tests/test_one.py", "pytest", "pytest"])
    assert s["first_tally"] == (500, 0) and s["last_tally"] == (512, 0), (s["first_tally"], s["last_tally"])


def test_test_command_detection():
    yes = ["pytest", "pytest -q tests/", "python3 -m pytest -x", "cd /x && python3 test_grade_session.py",
           "FORCE_COLOR=0 npx jest --ci", "npm test", "npm run test:unit", "go test ./...",
           "cargo test", "make test", "bash -lc 'cd x && pytest -q'", "uv run pytest", "pytest | tee log"]
    no = ["cat test_report.txt", "echo 'pytest: 999 passed'", "grep passed test_log.txt",
          "ls tests", "less test_x.log", "printf '10 passed'", "echo 'a; pytest'"]
    for c in yes:
        assert gs.is_test_command(c), f"missed runner: {c}"
    for c in no:
        assert not gs.is_test_command(c), f"accepted non-runner: {c}"
    s = _tally_session(["10 passed", "1000 passed"], cmd="cat test_report.txt")
    assert s["first_tally"] is None and "Test Whisperer" not in buff_names(s)


def _codex_file(rows, sid=UUID_A):
    d = tempfile.mkdtemp()
    p = os.path.join(d, f"rollout-2026-08-20T10-00-00-{sid}.jsonl")
    _write(p, [{"timestamp": "2026-08-20T10:00:00.000Z", "type": "session_meta",
                "payload": {"session_id": sid}}] + rows)
    return p


def _codex_call(cid, name, inp, output, ts="2026-08-20T10:00:05.000Z", custom=True):
    call = ({"type": "custom_tool_call", "call_id": cid, "name": name, "input": inp} if custom
            else {"type": "function_call", "call_id": cid, "name": name,
                  "arguments": json.dumps({"command": inp})})
    out = {"type": "custom_tool_call_output" if custom else "function_call_output",
           "call_id": cid, "output": output}
    return [{"timestamp": ts, "type": "response_item", "payload": call},
            {"timestamp": ts, "type": "response_item", "payload": out}]


def test_codex_apply_patch_is_not_a_command():
    body = "*** Begin Patch\n*** Add File: pytest_notes.txt\n+pytest\n*** End Patch"
    rows = (_codex_call("a", "apply_patch", body, "Exit code: 0\nWall time: 0 seconds\nOutput:\n10 passed")
            + _codex_call("b", "apply_patch", body, "Exit code: 0\nWall time: 0 seconds\nOutput:\n99 passed"))
    s = analyze(_codex_file(rows))
    assert s["first_tally"] is None, s["first_tally"]


def test_codex_success_reads_envelope_only():
    from harness_adapters import _codex_success
    cases = [
        ("Exit code: 0\nWall time: 0.1 seconds\nOutput:\nok", True),
        ("Exit code: 1\nWall time: 0 seconds\nOutput:\nfixture says Exit code: 0", False),
        ("fixture says Exit code: 0\nExit code: 1", None),
        ("done\nExit code: 0", None),
        ("Chunk ID: ab12\nWall time: 1 seconds\nProcess exited with code 0\nOriginal token count: 3\nOutput:\nok", True),
        ("Chunk ID: ab12\nWall time: 1 seconds\nProcess exited with code 2\nOutput:\nExit code: 0", False),
        ("Chunk ID: ab12\nWall time: 1 seconds\nProcess running with session ID 5\nOutput:\n", None),
        (json.dumps({"output": "Exit code: 0", "metadata": {"exit_code": 2}}), False),
        ([{"type": "input_text", "text": "Exit code: 0\nWall time: 0 seconds\nOutput:\nok"}], True),
        ("no exit info", None),
    ]
    for text, want in cases:
        assert _codex_success(text) is want, (text, _codex_success(text), want)


def test_gemini_usage_once_per_message():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "session-2026-08-20T10-00-abcd1234.jsonl")
    _write(p, [
        {"sessionId": "abcd1234", "projectHash": "ff"},
        {"id": "m1", "timestamp": "2026-08-20T10:00:01.000Z", "type": "gemini", "model": "gemini-3.7-flash",
         "tokens": {"input": 5, "cached": 5, "output": 3}},
        {"id": "m1", "timestamp": "2026-08-20T10:00:02.000Z", "type": "gemini", "model": "gemini-3.7-flash",
         "tokens": {"input": 6, "cached": 5, "output": 4}},
    ])
    s = analyze(p)
    assert s["tokens_in"] == 11 and s["tokens_out"] == 4, (s["tokens_in"], s["tokens_out"])
    assert s["models"] == {"gemini-3.7-flash": 1}, s["models"]


def test_claude_compaction_and_reminders_are_not_human():
    recs = [prompt()]
    recs.append({"type": "user", "isCompactSummary": True, "timestamp": "2026-08-19T10:00:00.000Z",
                 "message": {"content": [{"type": "text", "text": "summary"}]}})
    for i in range(55):
        recs.append(asst([tool_use("Bash", f"c{i}", command=f"step {i}")]))
        recs.append({"type": "user", "timestamp": "2026-08-19T10:01:00.000Z",
                     "message": {"content": [
                         {"type": "tool_result", "tool_use_id": f"c{i}", "is_error": False, "content": "ok"},
                         {"type": "text", "text": "<system-reminder>be nice</system-reminder>"}]}})
    s = analyze(write_fixture(recs))
    assert s["user_prompts"] == 1, s["user_prompts"]
    assert s["longest_cook"] == 55, s["longest_cook"]
    assert s["compactions"] == 1


def test_codex_one_human_per_turn():
    ctx = {"timestamp": "2026-08-20T10:00:01.000Z", "type": "response_item",
           "payload": {"type": "message", "role": "user",
                       "content": [{"type": "input_text", "text": "<environment_context>\n  <cwd>/x</cwd>"}]}}
    agents = {"timestamp": "2026-08-20T10:00:01.000Z", "type": "response_item",
              "payload": {"type": "message", "role": "user",
                          "content": [{"type": "input_text", "text": "# AGENTS.md instructions for /x"}]}}

    def turn(text, ts):
        return [{"timestamp": ts, "type": "response_item",
                 "payload": {"type": "message", "role": "user",
                             "content": [{"type": "input_text", "text": text}]}},
                {"timestamp": ts, "type": "event_msg", "payload": {"type": "user_message", "message": text}}]
    s = analyze(_codex_file([ctx, agents] + turn("go", "2026-08-20T10:00:02.000Z")
                            + turn("again", "2026-08-20T10:00:09.000Z")))
    assert s["user_prompts"] == 2, s["user_prompts"]
    only_items = [ctx, agents] + [r for r in turn("go", "2026-08-20T10:00:02.000Z") if r["type"] == "response_item"]
    s = analyze(_codex_file(only_items))
    assert s["user_prompts"] == 1, s["user_prompts"]


def test_non_object_records_are_skipped():
    from harness_adapters import list_sessions
    junk = [[], None, "x", 3, {"type": "assistant", "message": []}, {"type": "user", "message": "x"},
            {"type": "response_item", "payload": []}, {"type": "turn_context", "payload": None},
            {"type": "event_msg", "payload": "x"}, {"type": "gemini", "toolCalls": [[], None], "tokens": []},
            {"type": "assistant", "message": {"model": ["x"], "usage": {"input_tokens": "9"},
                                              "content": [{"type": "tool_use", "name": None, "input": []}]}}]
    d = Path(tempfile.mkdtemp())
    claude = d / f"{UUID_A}.jsonl"
    _write(claude, [prompt()] + junk)
    analyze(claude)
    analyze(_codex_file(junk))
    gem = d / "session-2026-08-20T10-00-abcd1234.jsonl"
    _write(gem, [{"sessionId": "abcd1234", "projectHash": "ff"}] + junk)
    analyze(gem)
    g = d / "11fe0000-0000-7000-8000-00000000000a"
    g.mkdir()
    (g / "summary.json").write_text("{}")
    _write(g / "events.jsonl", junk + [{"type": "tool_completed", "tool_name": [], "outcome": {}}])
    _write(g / "updates.jsonl", junk + [{"params": []}, {"params": {"update": []}}])
    analyze(g)
    home = Path(tempfile.mkdtemp())
    cdx = home / ".codex" / "sessions" / "2026" / "08" / "20"
    cdx.mkdir(parents=True)
    for i, first in enumerate(([], None, {"type": "session_meta", "payload": []})):
        _write(cdx / f"rollout-2026-08-20T10-00-0{i}-0a1b2c3d-1111-4000-8000-00000000000{i}.jsonl", [first])
    assert len(list_sessions(home)) == 3


def test_codex_plan_then_apply_patch_is_not_all_plan():
    plan = {"timestamp": "2026-08-20T10:00:01.000Z", "type": "turn_context",
            "payload": {"model": "gpt", "collaboration_mode": {"kind": "plan"}}}
    rows = [plan] + _codex_call("p", "apply_patch", "*** Begin Patch", "Exit code: 0\nOutput:\n")
    assert "All Plan No Game" not in buff_names(analyze(_codex_file(rows)))
    rows = [plan] + _codex_call("s", "shell", "ls", "Exit code: 0\nOutput:\n", custom=False)
    assert "All Plan No Game" in buff_names(analyze(_codex_file(rows)))


def test_modifiers_fire_for_other_harnesses():
    rows = []
    for i in range(5):
        rows += _codex_call(f"a{i}", "spawn_agent", "", "{}", custom=False)
    for i in range(4):
        rows += _codex_call(f"q{i}", "request_user_input", "", "{}", custom=False)
    s = analyze(_codex_file(rows))
    names = buff_names(s)
    assert "Middle Manager" in names and "Twenty Questions" in names, names
    assert gs.delegation_note(s)
    d = tempfile.mkdtemp()
    p = os.path.join(d, "session-2026-08-20T10-00-abcd1234.jsonl")
    calls = [{"id": f"r{i}", "name": "read_file", "args": {"path": "x"}, "status": "success"}
             for i in range(20)]
    _write(p, [{"sessionId": "abcd1234", "projectHash": "ff"},
               {"id": "m1", "timestamp": "2026-08-20T10:00:01.000Z", "type": "gemini", "toolCalls": calls}])
    assert "Bookworm" in buff_names(analyze(p))


def test_grok_tool_result_text_feeds_tallies():
    d = Path(tempfile.mkdtemp()) / "11fe0000-0000-7000-8000-00000000000b"
    d.mkdir()
    (d / "summary.json").write_text("{}")
    ev, up = [], []
    for i, n in enumerate((10, 12)):
        ev.append({"ts": f"2026-08-20T10:00:0{i}.000Z", "type": "tool_completed",
                   "tool_name": "run_terminal_command", "outcome": "success", "tool_call_id": f"t{i}"})
        up.append({"sessionUpdate": "tool_call", "toolCallId": f"t{i}", "rawInput": {"command": "pytest -q"}})
        up.append({"sessionUpdate": "tool_call_update", "toolCallId": f"t{i}",
                   "rawOutput": {"type": "terminal", "exit_code": 0, "output": f"{n} passed in 1s"}})
    _write(d / "events.jsonl", ev)
    _write(d / "updates.jsonl", up)
    s = analyze(d)
    assert s["first_tally"] == (10, 0) and s["last_tally"] == (12, 0), (s["first_tally"], s["last_tally"])


def test_completed_window_from_session_end():
    recs = [prompt(ts="2026-08-19T10:00:00.000Z")]
    for i in range(6):
        ts = f"2026-08-19T10:{i * 3:02d}:01.000Z"
        recs.append(asst([tool_use("Bash", f"w{i}", command=f"s{i}")], ts=ts))
        recs.append(result(f"w{i}", "ok", ts=ts))
    recs.append(prompt("thanks", ts="2026-08-19T10:25:00.000Z"))
    s = analyze(write_fixture(recs))
    assert s["clean_window_chain"] == 1, s["clean_window_chain"]


def test_code_hash_covers_adapters():
    import hashlib
    import harness_adapters
    h = hashlib.sha256()
    for f in (GS_PATH, Path(harness_adapters.__file__)):
        b = Path(f).read_bytes()
        name = Path(f).name.encode()
        h.update(len(name).to_bytes(4, "big") + name + len(b).to_bytes(8, "big"))
        h.update(b)
    assert f"code {h.hexdigest()[:8]}" in gs.fingerprint(_min_s()), gs.fingerprint(_min_s())


def test_grok_hash_covers_compaction_checkpoints():
    home = Path(tempfile.mkdtemp())
    now = datetime.now(timezone.utc)
    d = _grok_sess(home, "aa5a0000-0000-7000-8000-000000000019", n_green=2, start=now,
                   minutes=5, mtime=now.timestamp())
    a = analyze(d)
    (d / "compaction_checkpoints").mkdir()
    (d / "compaction_checkpoints" / "cp1").write_text("x")
    b = analyze(d)
    assert b["compactions"] == 1 and a["transcript_sha"] != b["transcript_sha"]


def test_night_shift_uses_explicit_zone():
    recs = [prompt(ts="2026-08-19T03:00:00.000Z")]
    for i in range(12):
        recs.append(asst([tool_use("Bash", f"n{i}", command="ls")], ts=f"2026-08-19T03:{i:02d}:10.000Z"))
        recs.append(result(f"n{i}", "ok", ts=f"2026-08-19T03:{i:02d}:20.000Z"))
    p = write_fixture(recs)
    utc = analyze(p, tz=gs.parse_zone("UTC"))
    east = analyze(p, tz=gs.parse_zone("+12:00"))
    assert utc["night_events"] >= 10 and east["night_events"] == 0
    assert "tz UTC+00:00" in gs.fingerprint(utc) and "tz UTC+12:00" in gs.fingerprint(east)


def test_output_destination_safety():
    d = Path(tempfile.mkdtemp())
    sess = d / f"{UUID_A}.jsonl"
    _write(sess, [prompt(), asst([tool_use("Bash", "t", command="ls")]), result("t", "ok")])
    before = sess.read_bytes()
    out = _cli([sess, "--html", sess], d)
    assert out.returncode != 0 and sess.read_bytes() == before, out.stderr
    existing = d / "card.html"
    existing.write_text("keep me")
    out = _cli([sess, "--html", existing], d)
    assert out.returncode != 0 and existing.read_text() == "keep me", out.stderr
    out = _cli([sess, "--html", existing, "--force"], d)
    assert out.returncode == 0 and "TERMINALLY COOKED" in existing.read_text(), out.stderr
    mask = os.umask(0)
    os.umask(mask)
    assert existing.stat().st_mode & 0o777 == 0o666 & ~mask
    target = d / "target.txt"
    target.write_text("target")
    link = d / "link.html"
    link.symlink_to(target)
    out = _cli([sess, "--html", link], d)
    assert out.returncode != 0 and target.read_text() == "target", out.stderr
    out = _cli([sess, "--html", link, "--force"], d)
    assert out.returncode == 0 and target.read_text() == "target" and not link.is_symlink(), out.stderr
    src_link = d / "src.html"
    src_link.symlink_to(sess)
    out = _cli([sess, "--html", src_link, "--force"], d)
    assert out.returncode != 0 and sess.read_bytes() == before, out.stderr
    assert not [p for p in d.iterdir() if p.name.startswith(".tc-")]


def test_pick_cap_bounds_today_shortlist():
    from datetime import timedelta
    home = Path(tempfile.mkdtemp())
    now = datetime.now(timezone.utc)
    today = now.replace(hour=12, minute=0, second=0, microsecond=0)
    for i in range(25):
        _grok_sess(home, f"{i:08x}-0000-7000-8000-000000000000", n_green=2,
                   start=today - timedelta(minutes=i), minutes=10, mtime=now.timestamp() - i)
    calls = []
    real = gs.analyze
    gs.analyze = lambda p, *a, **k: (calls.append(p), real(p, *a, **k))[1]
    try:
        gs.pick_juicy_session(home=home, now=now, live_ids=[], env={}, cwd=Path("/nowhere"))
    finally:
        gs.analyze = real
    assert len(calls) <= gs.PICK_ANALYZE_CAP, len(calls)


def test_parse_ts_variants():
    want = datetime(2026, 8, 19, 10, 0, 0, 123456, tzinfo=timezone.utc)
    assert gs.parse_ts("2026-08-19T10:00:00.123456789Z") == want
    assert gs.parse_ts("2026-08-19T10:00:00.1Z") == want.replace(microsecond=100000)
    assert gs.parse_ts("2026-08-19T10:00:00.12+0000") == want.replace(microsecond=120000)
    assert gs.parse_ts("2026-08-19T10:00:00") == want.replace(microsecond=0)
    assert gs.parse_ts("not a time") is None and gs.parse_ts(None) is None
    recs = [prompt(ts="2026-08-19T10:00:00.123456789Z"),
            asst([tool_use("Bash", "t", command="ls")], ts="2026-08-19T10:30:00.5Z"),
            result("t", "ok", ts="2026-08-19T10:30:01.5Z")]
    assert gs.duration_minutes(analyze(write_fixture(recs))) == 30


def test_html_shows_unknowns_and_tool_histogram():
    rows = _codex_call("u", "shell", "ls", "no exit info", custom=False)
    s = analyze(_codex_file(rows))
    html = render_html(s, pick_buffs(s), 1)
    assert "?1 unknown" in html, html
    assert "shell:1" in html, html



# ---------------------------------------------------------------- pre-push review (Sol)

LIVE = "5e551000-aaaa-4bbb-8ccc-000000000001"


def _refused(arg, env, home):
    try:
        gs.find_session(str(arg), home=home, env=env)
    except SystemExit as e:
        return "invoking" in str(e.code)
    return False


def test_alias_and_renamed_invoker_are_refused():
    home = Path(tempfile.mkdtemp())
    elsewhere = Path(tempfile.mkdtemp())
    rollout = Path(_codex_file(_codex_call("c", "shell", "ls", "Exit code: 0\nOutput:\n"), sid=LIVE))
    env = {"CODEX_THREAD_ID": LIVE}
    link = elsewhere / "other.jsonl"
    link.symlink_to(rollout)
    assert _refused(link, env, home), "symlink alias graded the live Codex session"
    assert analyze(link)["session_id"] == analyze(link)["transcript_sha"][:8]
    renamed = elsewhere / "renamed.jsonl"
    os.rename(rollout, renamed)
    assert _refused(renamed, env, home), "renamed copy graded the live Codex session"
    claude = elsewhere / "notes.jsonl"
    _write(claude, [dict(r, sessionId=LIVE) for r in
                    [prompt(), asst([tool_use("Bash", "t", command="ls")]), result("t", "ok")]])
    assert _refused(claude, {"CLAUDE_CODE_SESSION_ID": LIVE}, home)
    g = elsewhere / "my-grok-run"
    g.mkdir()
    (g / "summary.json").write_text(json.dumps({"info": {"id": LIVE, "cwd": "/x"}}))
    _write(g / "events.jsonl", [{"ts": "2026-08-20T10:00:00.000Z", "type": "turn_started"}])
    assert _refused(g, {"GROK_SESSION_ID": LIVE}, home)
    gem = elsewhere / "gem.jsonl"
    _write(gem, [{"sessionId": LIVE, "projectHash": "ff"},
                 {"id": "m", "timestamp": "2026-08-20T10:00:01.000Z", "type": "user"}])
    assert _refused(gem, {"CLAUDE_CODE_SESSION_ID": LIVE}, home)
    other = elsewhere / "other-work.jsonl"
    _write(other, [dict(r, sessionId=UUID_A) for r in [prompt()]])
    found, _ = gs.find_session(str(other), home=home, env=env)
    assert found == other


def test_model_and_effort_metadata_allowlisted():
    recs = [prompt()]
    for i, (m, e) in enumerate((("acme-private-repo", "acme-secret"),
                                ("mcp__acme-secret__deploy", "high"),
                                ("claude-opus-5-5", "xhigh"))):
        recs.append(asst([tool_use("Bash", f"m{i}", command="ls")], model=m, effort=e))
        recs.append(result(f"m{i}", "ok"))
    s = analyze(write_fixture(recs))
    assert s["models"] == {"other model": 2, "claude-opus-5-5": 1}, s["models"]
    assert s["efforts"] == {"other": 1, "high": 1, "xhigh": 1}, s["efforts"]
    assert "Model Hopper" in buff_names(s)
    buffs = pick_buffs(s)
    out = gs.render(s, buffs, 1) + gs.render_html(s, buffs, 1) + gs.share_caption(s, buffs, 1)
    assert "acme" not in out.lower(), "private model or effort text reached the card"
    for ok in ("claude-opus-5-5", "gpt-6-astra", "gpt-5.4-mini", "o3", "o4-mini", "codex-mini-latest",
               "gemini-3.8-flash", "grok-4.7", "grok-code-fast-1"):
        assert gs.display_model(ok) == ok, ok
    for bad in ("acme-private-repo", "Claude-Opus", "claude-", "claude-a b", "claude-x/y",
                "claude-" + "a" * 60, "openai/gpt-5", "o-mini", "gpt_5", "other"):
        assert gs.display_model(bad) == "other model", bad
    for e in ("minimal", "low", "medium", "high", "xhigh", "max"):
        assert gs.display_effort(e) == e
    assert gs.display_effort("ultra") == "other" and gs.display_effort("High") == "other"
    leaked = dict(_min_s(), models={"acme-private-repo": 1}, efforts={"acme": 1})
    assert "acme" not in gs.render_html(leaked, [], 1)


def test_output_flags_refuse_non_card_extensions():
    home = Path(tempfile.mkdtemp())
    work = Path(tempfile.mkdtemp())
    sess = Path(tempfile.mkdtemp()) / f"{UUID_A}.jsonl"
    _write(sess, [prompt(), asst([tool_use("Bash", "t", command="ls")]), result("t", "ok")])
    for flag, ext in (("--png", ".png"), ("--html", ".html")):
        out = _cli([flag, "a3a4d4fb", "--projects-dir", home], work, {"TERMINALLY_COOKED_HOME": str(home)})
        assert out.returncode == 2 and ext in out.stderr, (flag, out.returncode, out.stderr)
        assert "auto-pick" not in out.stderr and "no session" not in out.stderr, out.stderr
        out = _cli([flag, sess, "--projects-dir", home], work, {"TERMINALLY_COOKED_HOME": str(home)})
        assert out.returncode == 2, (flag, out.stderr)
    out = _cli([sess, "--html", "Card.HTML"], work)
    assert out.returncode == 0 and (work / "Card.HTML").exists(), out.stderr
    assert sorted(p.name for p in work.iterdir()) == ["Card.HTML"]
    docs = [Path(__file__).parent / n for n in ("SKILL.md", "README.md")]
    docs += [Path(__file__).parent / "docs" / "engineering" / "architecture.md"]
    import re as _re
    bad = _re.compile(r"grade_session\.py\b[^\n`]*--(?:png|html)\s+(?!-|\[|#|$)(?!\S+\.(?:png|html)\b)\S+",
                      _re.MULTILINE)
    for doc in docs:
        hits = bad.findall(doc.read_text())
        assert not hits, f"{doc.name} puts a session after --png/--html: {hits}"
    help_text = _cli(["--help"], work).stdout
    assert "session first" in help_text.replace("\n", " ").replace("  ", " "), help_text


def test_compound_commands_never_score_tallies():
    poison = 'echo \';\' pytest "$(cat test_report.txt)"'
    s = _tally_session(["10 passed", "1000 passed"], cmd=poison)
    assert s["first_tally"] is None, s["first_tally"]
    s = _tally_session(["10 passed", "1000 passed"], cmd="pytest >/dev/null; cat test_report.txt")
    assert s["first_tally"] is None, s["first_tally"]
    s = _tally_session(["10 passed", "1000 passed"], cmd="pytest | cat -<test_report.txt")
    assert s["first_tally"] is None, s["first_tally"]
    s = _tally_session(["10 passed", "12 passed"], cmd="cd x && pytest -q")
    assert s["first_tally"] == (10, 0) and s["last_tally"] == (12, 0)
    yes = ["cd x && pytest -q", 'cd "a b" && FOO=1 pytest', "FOO=1 && pytest", "pytest -q 2>&1",
           "pytest 2>/dev/null", "bash -lc 'cd x && pytest -q'", "pytest -k 'a or b; c'",
           "cd x && cd y && python3 -m pytest", "pytest\n", "pytest | grep -vi warn | tail -n5",
           "pytest | grep -Ec passed", "pytest | sort -nr | head -c 400", "pytest | tail -20",
           "pytest | tee log", "pytest -q 2>&1 | tail -20", 'cd x && npm test 2>&1 | grep -E "passed|failed"',
           "pytest 2>&1 | grep -v warn | tail -n 5", "pytest | head -3", "pytest | sort | cat", "pytest | less",
           "pytest | tee -a log | tail -5", "pytest | grep -e passed -e failed"]
    no = ["pytest | echo 1000 passed", "pytest | sh -c 'cat report'", "pytest | cat report.txt",
          "pytest | grep passed report.txt", "pytest | tail -5 > out", "pytest | tail -5; cat r.txt",
          "pytest | xargs echo", "pytest | tail $(cat n)", "pytest | printf '9 passed'", "cat r.txt | pytest",
          "pytest | head -n", "pytest | sort report.txt", "pytest > log",
          "pytest | cat -<test_report.txt", "pytest | grep -H --label='1000 passed' .",
          "pytest | sort --files0-from=x", "cat -<r.txt", "pytest | cat -<r.txt", "pytest | tail -5 < r.txt",
          "pytest < /dev/null", "pytest <<EOF", "pytest | grep -f pats", "pytest | grep -r passed",
          "pytest | tail -f", "pytest | tail -n +3", "pytest | tee -p log", "pytest | cat -",
          "pytest | less -R", "pytest | sort -k 2", "pytest | grep -e", "pytest | grep -- passed", "pytest >> log", "pytest 1>log",
          "pytest &> log", "pytest >& log", "pytest; echo done", "pytest && cat report.txt",
          "pytest || true", "pytest &", "echo `pytest`", "pytest $(cat args)", 'pytest "$(cat args)"',
          "(cd x && pytest)", "cd x; pytest", "make build && pytest", "echo ';' pytest",
          "cd x y && pytest", "pytest\ncat report.txt", "bash -lc 'pytest; cat r.txt'"]
    for c in yes:
        assert gs.is_test_command(c), f"missed runner: {c!r}"
    for c in no:
        assert not gs.is_test_command(c), f"scored ambiguous command: {c!r}"


def test_valid_json_shapes_do_not_crash():
    from harness_adapters import detect_harness
    d = Path(tempfile.mkdtemp())
    a = d / f"{UUID_A}.jsonl"
    _write(a, [{"type": [], "payload": {}}, prompt(),
               asst([tool_use("Bash", "t", command="ls")]), result("t", "ok")])
    assert detect_harness(a) == "claude-code"
    assert analyze(a)["green"] == 1
    out = _cli([a], d)
    assert out.returncode == 0 and "Traceback" not in out.stderr, out.stderr
    b = d / "b.jsonl"
    _write(b, [prompt(), asst([{"type": "tool_use", "name": "Bash", "id": [], "input": {"command": "pytest"}}]),
               {"type": "user", "timestamp": "2026-08-19T10:01:00.000Z",
                "message": {"content": [{"type": "tool_result", "tool_use_id": {}, "content": "1 passed"}]}},
               asst([{"type": ["tool_use"], "name": "Bash", "id": "x"}])])
    s = analyze(b)
    assert s["tools"] == {"Bash": 1} and s["first_tally"] is None, (s["tools"], s["first_tally"])
    rows = [{"timestamp": "2026-08-20T10:00:05.000Z", "type": "response_item",
             "payload": {"type": "function_call", "call_id": [], "name": "shell",
                         "arguments": json.dumps({"command": "pytest"})}},
            {"timestamp": "2026-08-20T10:00:06.000Z", "type": "response_item",
             "payload": {"type": "function_call_output", "call_id": [], "output": "Exit code: 0\nOutput:\n5 passed"}},
            {"timestamp": "2026-08-20T10:00:07.000Z", "type": "response_item",
             "payload": {"type": {}, "role": [], "content": []}},
            {"timestamp": "2026-08-20T10:00:07.000Z", "type": {"x": 1}, "payload": {"type": "user_message"}}]
    s = analyze(_codex_file(rows))
    assert s["green"] == 1 and s["first_tally"] is None, (s["green"], s["first_tally"])


def test_final_timestamps_survive_dedup_and_silent_records():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "session-2026-08-20T10-00-abcd1234.jsonl")
    calls = [{"id": f"g{i}", "name": "read_file", "args": {}, "status": "success"} for i in range(6)]
    _write(p, [{"sessionId": "abcd1234", "projectHash": "ff"},
               {"id": "u", "timestamp": "2026-08-20T10:00:00.000Z", "type": "user"},
               {"id": "m1", "timestamp": "2026-08-20T10:00:00.000Z", "type": "gemini", "model": "gemini-3.8-flash",
                "toolCalls": calls},
               {"id": "m1", "timestamp": "2026-08-20T10:25:00.000Z", "type": "gemini", "model": "gemini-3.8-flash",
                "toolCalls": calls, "tokens": {"input": 9, "output": 2}}])
    s = analyze(p)
    assert s["clean_window_chain"] == 1, s["clean_window_chain"]
    assert gs.duration_minutes(s) == 25 and s["green"] == 6 and s["models"] == {"gemini-3.8-flash": 1}
    rows = []
    for i in range(6):
        rows += _codex_call(f"c{i}", "shell", "ls", "Exit code: 0\nOutput:\n",
                            ts=f"2026-08-20T10:00:0{i}.000Z", custom=False)
    night = gs.parse_zone("-07:00")              # 10:xx UTC is 03:xx here
    base = analyze(_codex_file(rows), tz=night)
    assert base["night_events"] > 0
    final = {"timestamp": "2026-08-20T10:25:00.000Z", "type": "response_item",
             "payload": {"type": "message", "role": "assistant",
                         "content": [{"type": "output_text", "text": "done"}]}}
    reasoning = [{"timestamp": f"2026-08-20T10:0{i}:30.000Z", "type": "response_item",
                  "payload": {"type": "reasoning", "summary": []}} for i in range(5)]
    s = analyze(_codex_file(rows + reasoning + [final]), tz=night)
    assert s["clean_window_chain"] == 1 and gs.duration_minutes(s) == 25, (s["clean_window_chain"], s["last_ts"])
    for k in ("night_events", "green", "user_prompts", "longest_streak", "longest_cook", "unknown_results"):
        assert s[k] == base[k], (k, s[k], base[k])


def test_codex_xml_prompt_is_a_human_turn():
    def user(text, ts):
        return {"timestamp": ts, "type": "response_item",
                "payload": {"type": "message", "role": "user",
                            "content": [{"type": "input_text", "text": text}]}}
    rows = [user("<environment_context>\n  <cwd>/x</cwd>\n</environment_context>", "2026-08-20T10:00:01.000Z"),
            user("<user_instructions>\nbe terse\n</user_instructions>", "2026-08-20T10:00:01.000Z"),
            user("# AGENTS.md instructions for /x\n\n<INSTRUCTIONS>", "2026-08-20T10:00:01.000Z"),
            user("<heartbeat>\n  <automation_id>x</automation_id>\n</heartbeat>", "2026-08-20T10:00:01.000Z"),
            user("start", "2026-08-20T10:00:02.000Z")]
    for i in range(30):
        rows += _codex_call(f"a{i}", "shell", "ls", "Exit code: 0\nOutput:\n", custom=False)
    rows.append(user("<task>Continue with the next change</task>", "2026-08-20T10:10:00.000Z"))
    for i in range(30):
        rows += _codex_call(f"b{i}", "shell", "ls", "Exit code: 0\nOutput:\n",
                            ts="2026-08-20T10:10:05.000Z", custom=False)
    s = analyze(_codex_file(rows))
    assert s["user_prompts"] == 2, s["user_prompts"]
    assert s["longest_cook"] == 30, s["longest_cook"]


def test_no_force_publish_fails_closed_without_hardlinks():
    import errno
    d = Path(tempfile.mkdtemp())
    dest = d / "card.html"
    real = gs.os.link

    def no_links(*a, **k):
        raise OSError(errno.EPERM, "Operation not permitted")
    gs.os.link = no_links
    try:
        try:
            gs.write_output(dest, "card")
        except gs.OutputError as e:
            assert "--force" in str(e), e
        else:
            raise AssertionError("published without an exclusive create")
        assert not os.path.lexists(dest)
        gs.write_output(dest, "card", force=True)
        assert dest.read_text() == "card"
    finally:
        gs.os.link = real
    assert not [p for p in d.iterdir() if p.name.startswith(".tc-")]



def test_renamed_transcript_without_jsonl_suffix_is_refused():
    home = Path(tempfile.mkdtemp())
    d = Path(tempfile.mkdtemp())
    notes = d / "notes.txt"
    _write(notes, [dict(r, sessionId=LIVE) for r in
                   [prompt(), asst([tool_use("Bash", "t", command="ls")]), result("t", "ok")]])
    xlog = d / "x.log"
    xlog.write_bytes(Path(_codex_file(_codex_call("c", "shell", "ls", "Exit code: 0\nOutput:\n"),
                                      sid=LIVE)).read_bytes())
    for path, env in ((notes, {"CLAUDE_CODE_SESSION_ID": LIVE}), (xlog, {"CODEX_THREAD_ID": LIVE})):
        assert _refused(path, env, home), f"graded the live session via {path.name}"
        out = _cli([path, "--projects-dir", home], d, dict(env, TERMINALLY_COOKED_HOME=str(home)))
        assert out.returncode != 0 and "invoking" in out.stderr, (path.name, out.returncode, out.stderr)
        assert "TERMINALLY COOKED" not in out.stdout
    out = _cli([xlog, "--projects-dir", home], d, {"TERMINALLY_COOKED_HOME": str(home)})
    assert out.returncode == 0 and "codex" in out.stdout.lower(), out.stderr


if __name__ == "__main__":
    fails = 0
    tests = sorted({k: v for k, v in globals().items() if k.startswith("test_")}.items())
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as e:   # a crash is a failure, not an abort of the run
            fails += 1
            print(f"FAIL {name}: {type(e).__name__}: {e}")
    print(f"\n{'FAILED' if fails else 'OK'} — {len(tests)} tests, {fails} failures")
    sys.exit(1 if fails else 0)
