---
version: "1.0.0"
schema_version: 2
title: "Badge Style Guide (template v3.1)"
doc_type: detail
parent: INDEX.md
last_updated: 2026-08-19
last_audit: 2026-08-19
audit_status: current
domain: docs
triggers:
  - "badge style guide"
  - "art template"
  - "focus mode"
  - "canonical direction"
---
# Badge Style Guide (template v3.1)

**Every badge is painterly splash art in luminous saturated color, built around one central subject with a strong silhouette, containing no text whatsoever, and declaring both a focus mode and a canonical direction.** These rules exist so 24 images made by two different models read as one series and survive being shrunk to a 32-pixel tile.

## The template

Every prompt is prefixed with the shared template and then adds its own scene:

> Square composition. Painterly splash art — visible oil brushwork, dynamic baroque staging — with bright, luminous, sun-lit color: rich saturated pigments, radiant light, glowing highlights, deep clean shadows. Not neon, not electric, not tone-mapped; and never gray, dusty, or pastel. Strong dark-silhouette read with rim-light halo so it pops on dark backgrounds at small sizes. Minimal clutter. Absolutely no text anywhere. No logos, no real people, no terminal-green matrix glow, no circuitry.

## Focus modes

Every prompt declares exactly one. This exists because a single framing rule destroyed a joke: an early "subject fills 70%, medium-close" rule cropped away the wall in DOOM LOOP — and the wall, with its two identical craters, *was* the joke.

| Mode | When | Framing rule |
|---|---|---|
| **FOCUS: PERSON** | the character carries the joke | character fills 65–70%, medium-close, environment simplified to a radiant backdrop plus one ground band |
| **FOCUS: ENVIRONMENT** | the scene carries the joke | wider framing; joke elements specified by count, placement and sameness; character ~35% but silhouette-clear |

## Canonical direction

Image models treat "on the left" as a suggestion, and inconsistent facing across a set is immediately visible. Each badge therefore records a canonical direction, stated **redundantly** in its prompt — once as motion ("all horses in profile facing left, action reads right-to-left") and once as placement ("craters occupy the left half; the knight enters on the right"). Compliance is then verified mechanically rather than trusted; see [production-pipeline.md](./production-pipeline.md).

## Color direction

Luminous and saturated, lit as if from within, with the scene's own palette — terracotta and cobalt for a sunbaked wall, teal and coral for a wave at sunrise. Three vocabularies are explicitly banned because each was tried and failed:

| Rejected | Why |
|---|---|
| Terminal green, circuitry, void-black grounds | reads as generic "cyber", and dissolves into the card's dark background |
| "HDR" as a prompt word | models map it to 2010s tone-mapped photography — flat, grey-lifted, muted |
| Neon / electric grading | overshoots into glossy digital and loses the painterly texture that makes the set feel handmade |

Post-processing applies a modest vivid grade (saturation +18%, contrast +6%) and tags the file with a Display P3 profile so wide-gamut screens render the extra chroma.

## Composition rules

1. One subject, one punchline. No collages, no second story in the corners.
2. Silhouette first — the subject must be identifiable as a black shape.
3. Rim light always, so the subject separates from a dark UI.
4. Ground band in the lower third to anchor the scene.
5. High-frequency micro-detail is a liability; it turns to noise at 32 px.

## Prohibitions

No text of any kind in the image — no plaques, no signage, no numbers. No logos, no real people, no recognisable characters. No emoji-styled or sticker-flat treatments. Names are typography drawn by the card renderer, which is the only way to make them identical across a set.

## Provenance

The rules above are the surviving output of three iterations: a Terminal-Mythology direction that was too cyber, a hypersaturated electric direction that lost the painterly quality, and the present painterly-luminous synthesis. The 32 px legibility rules and the no-text ruling come from a game-industry icon review of the rendered set — see [research/review-ledgers.md](../research/review-ledgers.md).
