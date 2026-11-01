---
version: "1.0.0"
schema_version: 2
title: "Badge Production Pipeline"
doc_type: detail
parent: INDEX.md
last_updated: 2026-08-20
last_audit: 2026-08-19
audit_status: current
domain: docs
triggers:
  - "badge pipeline"
  - "generate badge art"
  - "orientation gate"
  - "badge LOD"
---
# Badge Production Pipeline

**Five deterministic stages take a badge concept to shippable assets: prompt, render on both models, orientation gate, grade and tag, emit level-of-detail set.** Every failure mode found during the pilot has a mechanical guard in this chain, so quality does not depend on inspecting 48 images by eye.

## Stages

| # | Stage | Tool | Guarantee |
|---|---|---|---|
| 1 | Prompt | `prompt_<slug>.txt` | template v3.1 + focus mode + canonical direction, textless |
| 2 | Render | `gen_grok.py` (xAI `grok-imagine-image-quality`), Codex built-in `image_gen` | square masters from two models on identical prompts |
| 3 | Orientation gate | `check_orientation.py`, `orientation_gates.sh` | canonical direction enforced, auto-mirrored when violated |
| 4 | Grade | `postprocess.py` | saturation +18%, contrast +6%, Display P3 profile |
| 5 | LOD emit | `postprocess.py` | `icon_1024`, `icon_72`, `icon_32` per badge per model |

Pipeline scripts and masters are local scratch, not this repo. Only winning 32/72 px derivatives are committed under `assets/badges/`.

## Stage detail

**Render.** Both lanes take the identical prompt so a later vote measures the model, not the prompt. The xAI lane accepts `aspect_ratio: "1:1"` natively and returns 1024×1024; the Codex lane is instructed to render square and is normalised in stage 4 regardless. The xAI driver is a Python script rather than shell: an early shell version silently produced 21 empty files because nested quoting broke the JSON payload, which is why the driver now owns the request end to end and retries once per image.

**Orientation gate.** For direction-critical badges, a vision model answers a strict yes/no question about layout ("are the craters in the left half with the knight on the right?"). A `NO` triggers a lossless horizontal mirror; an unparseable answer leaves the file untouched and flagged rather than guessing. This is only safe because the art is textless — mirroring a painted nameplate would destroy it.

**Grade and LOD.** Masters are center-cropped square and resized to 1024. The 32 px asset is not a naive downscale: it is a 62% center-zoom crop with additional contrast and saturation, because at tile size a full-frame composition loses its subject. All three levels carry the P3 profile.

## Running it

Work in a local scratch directory that is **not** this git tree. Put the prompt files, driver scripts, and masters there. Export whichever image-provider key your driver needs from your own secret store — never commit keys, and never add a fetch to `grade_session.py`.

```bash
python3 gen_grok.py <slug> [<slug> ...]      # metered image lane (optional)
bash orientation_gates.sh                     # direction gate + auto-mirror
python3 postprocess.py                        # grade, P3 tag, LOD set
open gallery.html                             # blind A/B review
```

A second model lane (for the blind vote) should use the identical prompt and write a square PNG next to the first. Codex `image_gen` is one such lane: anchor `codex exec` at a directory that already has an instruction file, reach scratch via `--add-dir`, and close stdin (`< /dev/null`). Promote only the voted 32 px and 72 px files into `assets/badges/`.

## Cost and volume

One image per badge per model — 48 masters, 144 derivatives. Variants are a winners-only second pass, deliberately: rendering three variants of a losing badge wastes budget. The Codex lane is subscription-billed at no marginal cost; the xAI lane is metered at cents per image.

## Known fragilities

- Image models occasionally return a malformed response; the driver retries once, then reports and continues rather than aborting the batch.
- The orientation gate depends on a vision model's yes/no discipline; an ambiguous answer is treated as "leave alone", never as a mirror.
- Codex renders are slower than the API lane by roughly an order of magnitude, so batches run in the background.
