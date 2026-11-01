---
name: desk-bench
description: >
  Run DeskBench, the joke benchmark that asks whether a newly released AI
  model can clean up a messy desktop. It builds a fake desktop in a temp
  folder, runs an agent CLI on it inside that CLI's write sandbox, scores
  the end state as a Rube Goldberg machine, and moves the sandbox to the
  Trash. Use when the user says "run deskbench", "desk bench", "desktop
  benchmark", "can the new model clean my desktop", "a new model dropped",
  or asks to add a model to the DeskBench leaderboard.
---

# DeskBench

Run the CLI in this folder. Do not reimplement scoring, and never point an
agent at a real desktop.

```bash
python3 desk_bench.py run claude-code --model <model-id>         # try it, nothing saved
python3 desk_bench.py run claude-code --model <model-id> --save  # a leaderboard row
python3 desk_bench.py run codex --model <model-id> --save
python3 desk_bench.py run codex --save --model <id> --slow   # dramatic version
python3 desk_bench.py clean --dry-run                         # list leftovers
python3 desk_bench.py clean                                   # move them to the Trash
python3 test_desk_bench.py
```

`run` does the whole cycle in one call:

1. Builds a fresh fake desktop in a new `desk-bench-*` temp folder.
2. Runs the agent with that desktop as its working directory. Codex gets
   `-s workspace-write` with every enabled MCP server switched off (they run
   outside its sandbox; the run refuses to start if one stays on). Claude
   Code gets only sandboxed Bash with no unsandboxed fallback, plus Read,
   Glob and Grep, and no MCP servers. The user's own CLI hooks and settings
   still run unsandboxed; do not claim they are confined.
3. Scores the end state and prints the agent's last lines and the machine
   card. On a timeout it kills the agent's process tree first, best effort:
   a process the agent detached into its own session can survive.
4. With `--save`, writes `results/<date>_<model>_<harness>_seed<N>.json` and
   rebuilds `LEADERBOARD.md`. A run that timed out or exited with an error
   is shown but never saved, and `run` exits 1.
5. Moves the sandbox to the Trash, whatever happened above. `--keep` leaves
   it in place to inspect; run `clean` afterwards.

Every check that can fail (`--save` without `--model`, an existing result
without `--force`, no Trash, CLI not on PATH) runs before the agent starts.

## Rules

- **Nothing outside a sandbox is deleted.** The agent under test may delete
  files inside its fake desktop; that is the test. Sandboxes go to the
  Trash. `clean` and `trash_sandbox` refuse any folder without a valid
  DeskBench marker file. Do not replace them with `rm`.
- **Running from inside another agent.** If your own shell is sandboxed,
  `run` may fail to reach `~/.Trash` or to start the agent's own sandbox
  inside yours. Ask for the command to run outside your sandbox rather than
  loosening the agent's flags.
- **Sandbox flags are not optional.** Never run an agent with
  `--dangerously-bypass-approvals-and-sandbox`, `bypassPermissions`, `--yolo`,
  or from a real `~/Desktop`. A harness without a write sandbox is not
  supported; say so rather than running it unsandboxed.
- **One run per model, standard seed 0** for leaderboard rows. Re-running the
  same model the same day needs `--force`; mention that the earlier row is
  replaced.
- **Saving is local.** Commit and push a new result only when the user asks.
- Show the machine card as printed. Do not summarize the score away, and keep
  the entertainment line.
- **Report failures plainly.** If the agent failed, timed out or cleanup
  could not finish, say so, and give the sandbox path `run` printed if it
  was kept.

## Repair without breaking intent

When an agent CLI changes its flags, fix `agent_command` and its test, and
keep the sandbox guarantee. Check the CLI's own `--help` first.

**Forbidden without an explicit owner decision and a new `SCORING_VERSION`**
- Changing points, penalties, thresholds, the fixture, or the prompt
- Tuning the scorer after seeing a model's result so that model scores better
- Adding network calls, telemetry, or uploads
- Removing the entertainment label

Fixture or prompt changes invalidate every saved result: re-run the board on
the new version. A scoring-only change can instead re-score the saved
desktops in the Trash with `score --save --force`, keeping each run's date.
The leaderboard shows only the current `SCORING_VERSION` on seed 0.
