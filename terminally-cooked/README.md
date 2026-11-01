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
python3 grade_session.py            # auto-pick; check the selection limits below
python3 grade_session.py --png      # also write a tightly cropped PNG and open it
python3 grade_session.py a3a4d4fb   # session-uuid prefix
python3 grade_session.py path/to/session.jsonl
python3 grade_session.py --html     # standalone HTML card
python3 grade_session.py --share    # copy a caption; you paste it
python3 test_grade_session.py       # 57 tests
python3 grade_session.py --help
```

Never grade the invoking session. Auto-pick excludes recognized harness IDs and uses recency fallbacks that can exclude the wrong session when identity is uncertain. Use a known other session, or abstain if it cannot be established. See [the selection limits](./docs/engineering/architecture.md#auto-pick-selection-and-limits).

Python 3.9+, stdlib only. Badge PNGs live in `assets/badges/` and ride along
in the clone. HTML cards embed them as data URIs, so producing a card does not
hit the network.

Point a Codex rollout, a Grok session directory, or a Gemini chat file at the
same CLI. Clone this repo into your agent's skill path if you want the bundled
[SKILL.md](./SKILL.md) — it tells the agent how to grade, and what it may
repair when a transcript format drifts.

## Privacy

Nothing leaves the machine. There is no network code on the grading path. Card
fields are allowlisted — no prompt text, file paths, repo names, or tool output —
and a test enforces it. Sharing a card is something you do. Full contract:
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

Scoring v0.5, 24 modifiers, 57 tests. Known coupling: each CLI's session
format can change. Adapters fail open; breakage is a degraded card, not a
crash. See
[docs/engineering/transcript-observables.md](./docs/engineering/transcript-observables.md).
