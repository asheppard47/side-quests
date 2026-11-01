# Contributing

Clone this repo and keep `assets/badges/` and `assets/logo.png` next to
`grade_session.py`. Cards embed those PNGs as data URIs so a grade costs nobody
bandwidth.

```bash
python3 test_grade_session.py
python3 grade_session.py --help
```

Python 3.9+ from the stdlib. No pip install.

## What to send

**Harness adapters.** New or broken transcript shapes belong in
`harness_adapters.py` plus a fixture test. Fail open on unknown records. Do not
guess tool outcomes. See `docs/design/harness-adapters.md` and `SKILL.md`
(repair-without-breaking-intent).

**Catalog jokes.** A new modifier needs: an observable the transcript actually
contains, a name that punches at the session not the person, a test, and a row
in `docs/design/modifier-catalog.md`. Flavor adds; only serialized-success
chains multiply.

**Badge art.** Follow `docs/art/style-guide.md` (painterly, luminous, textless,
one subject). Do not paint the achievement name into the image. Winners ship as
`assets/badges/<slug>_32.png` and `_72.png`.

**Docs.** Fix stale claims. Do not add private machine paths, API keys, or
transcript excerpts.

## What not to send

- Network code on the grading path (upload, telemetry, CDN badge URLs, "just a
  POST of the card")
- Leaderboards, rankings, or fairness claims
- Scoring-formula tweaks bundled with an unrelated parser fix
- Real session transcripts, prompts, repo names, or secrets
- Changes that put a new field on the card without an allowlist test

Scoring changes need a new `SCORING_VERSION` string and tests for the old
invariants (allowlist, fail-open unknowns, no network, entertainment label).

## Pull requests

One concern per PR. Tests green. If you change card fields or HTML, run
`test_html_card_allowlist` and `test_badge_art_embedded_without_paths` and
paste that they passed.

Issues for "my harness file grades as empty / unknown" should include: harness
name, a redacted record *shape* (keys only, no prompt text), and the adapter
stamp printed on the card. Never paste a real transcript.
