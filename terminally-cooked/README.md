# Terminally Cooked

An AI coding session roast. Grade one of your own agent sessions into a comedy
results card, in the red/green diff-counter look. Local-only: it reads a
session file already on your disk, counts what happened, stamps named
achievements, and prints a card. The score is entertainment and says so.

Supported harnesses (auto-detected from the file's own shape): **Claude Code**,
**Codex CLI**, **Grok CLI**, **Gemini CLI**. Cross-harness scores are different
games. The card stamps which adapter produced it.

```bash
git clone https://github.com/asheppard47/side-quests.git
cd side-quests/terminally-cooked
python3 grade_session.py --png                  # auto-pick from today; cropped PNG + HTML
python3 grade_session.py a3a4d4fb --png         # a session-id prefix (session first)
python3 grade_session.py path/to/session --png  # a file, or a Grok session dir
python3 grade_session.py --html                 # standalone HTML card only
python3 grade_session.py --share                # copy a caption; you paste it
python3 test_grade_session.py                   # 100 tests
python3 grade_session.py --help
```

Never grade the invoking session. When the invoking harness exposes its session id (`CLAUDE_CODE_SESSION_ID`, `CODEX_THREAD_ID`, `GROK_SESSION_ID`, and the others `--help` lists), auto-pick excludes that session and an explicit target matching it is refused. Without an id, auto-pick excludes the newest session of every harness and the newest in this project, and its note says the exclusion was a heuristic. See [the selection limits](./docs/engineering/architecture.md#auto-pick-selection-and-limits).

Python 3.9+, stdlib only. Badge PNGs live in `assets/badges/` and ride along
in the clone. HTML cards embed them as data URIs and carry a Content Security
Policy that allows only inline styles and `data:` images. Card files are never
overwritten without `--force`.

Point a Codex rollout, a Grok session directory, or a Gemini chat file at the
same CLI. Clone this repo into your agent's skill path if you want the bundled
[SKILL.md](./SKILL.md) — it tells the agent how to grade, and what it may
repair when a transcript format drifts.

## Privacy

Nothing is uploaded. The grading code has no network client. `--png` launches
your local Chrome with its background services switched off and every host name
mapped to nothing, on a page whose CSP blocks remote loads; those are the
enforced controls, not a network-traffic audit. Card fields are allowlisted (no
prompt text, file paths, repo names, tool output, or raw tool names), terminal
control characters are stripped from everything printed, and tests enforce
both. Sharing a card is something you do. Full contract:
[docs/product/privacy-contract.md](./docs/product/privacy-contract.md).

## License

[MIT](../LICENSE). [Contributing](./CONTRIBUTING.md).

## Docs

[INDEX.md](./INDEX.md) is the tree.

| Section | Owns |
|---|---|
| [docs/product/](./docs/product/INDEX.md) | Concept, privacy contract, decision log |
| [docs/design/](./docs/design/INDEX.md) | Scoring model, modifier catalog, card spec |
| [docs/art/](./docs/art/INDEX.md) | Badge style, production, voting |
| [docs/engineering/](./docs/engineering/INDEX.md) | Architecture, transcript observables, testing |
| [docs/research/](./docs/research/INDEX.md) | External review ledgers |

## Status

Scoring v0.6, 24 modifiers, 100 tests. Known coupling: each CLI's session
format can change. Adapters skip malformed lines, non-object records and record
types they do not know, so format drift usually shows up as a sparser card. A
shape the guards do not anticipate can still stop a run with an error; report
it as an adapter bug. See
[docs/engineering/transcript-observables.md](./docs/engineering/transcript-observables.md).
