# SPEC — Video generation: asset-forge video mode + frame-sampled QA

**Status: APPROVED 2026-07-09 (touchpoint 1) with rulings:**
1. AMENDED by approver: **Seedance 2.0 has native audio** — audio-bearing briefs do
   NOT route away from it. Both `ASSET_VIDEO_MODEL_DEFAULT` and
   `ASSET_VIDEO_MODEL_AUDIO` default to the Seedance 2.0 Fast id; the AUDIO key
   remains an override seam (Veo 3.1 is the documented alternative if audio
   sync quality disappoints).
2. `ASSET_VIDEO_MAX_COST_USD` default 5.00 — ratified.
3. QA frame count default 10 — ratified.
4. Audio-track QA deferred to its own spec (visual-only, fail-closed) — ratified.
Date: 2026-07-09. Author: lead (planner role).

## Goal
Extend the asset pipeline to VIDEO: agents generate video assets (presentation
clips, UI motion demos, project footage) via Atlas Cloud video models, QA'd the
same way images are — explicit acceptance criteria, cross-family judge, bounded
loop, panel escalation on exhaustion, provenance sidecar. The "eyes" are frame
sampling (ffmpeg, now installed) — the mechanism the vendored watch-video skill
already proves out.

## What already exists (all shipped + gated)
- `panel/asset_qa.py`: judge, cross-family picker, ForgeLoop, sidecar — the loop
  machinery is video-agnostic already.
- `panel/attachments.py`: multiple image parts in one call (frames are images).
- `.claude/skills/watch-video/` (vendored, pinned): ffmpeg frame extraction +
  transcript pipeline; ffmpeg/ffprobe/yt-dlp installed 2026-07-09.
- Atlas Cloud MCP serves the major video models under one key. Verified pricing
  (2026-07-09, atlascloud.ai): Seedance 2.0 Fast ~$0.022/sec · Veo 3.1 ~$0.03/sec
  (native audio) · Kling 3.0 Std $0.084–0.126/sec · Sora 2 ~$0.15/sec ·
  Seedance Pro ~$0.247/sec. Exact Atlas model ids MUST be discovered via the
  MCP's model-discovery tool at generation time — never assumed.

## Design

### A. `judge_video` (panel/asset_qa.py — Wave 1)
1. **Frame sampling**: extract N frames (default 10: first, last, 8 evenly spaced)
   via ffmpeg with timestamp labels. The extractor is an injectable seam (like the
   adapter's transport) so the mocked gate never shells out; one integration test
   synthesizes a video LOCALLY with ffmpeg (`color`/`testsrc` source — free) and
   extracts real frames, skipped where ffmpeg is absent.
2. **One judge call**: all sampled frames as image parts, each preceded by a
   `t=<seconds>` text label, + the acceptance criteria. Same strict schema, same
   fail-closed sanitizer, same cross-family rule (judge family ≠ VIDEO generator
   family). Temporal criteria ("logo appears by t=2s", "no flicker") are judged
   from the labeled sequence.
3. **Scope guard**: visual-track QA ONLY in this spec. If criteria mention audio,
   the judge is told to mark those criteria unverifiable (= fail closed) and the
   sidecar records `audio_qa: "not-performed"`. Audio QA (transcript via
   watch-video/Whisper) is a follow-up spec.
4. CLI: `python -m panel.asset_qa --video <path> ...` (same exits 0/2/3).

### B. Skill + config + UI (Waves 2–3)
- asset-forge gains a VIDEO branch: generator = `ASSET_VIDEO_MODEL_DEFAULT`
  (audio-bearing briefs → `ASSET_VIDEO_MODEL_AUDIO`); loop/sidecar/escalation
  identical; per-attempt generation cost from the MCP result feeds ForgeLoop.
- New keys (dashboard-editable, Rule 11 mockup first):
  `ASSET_VIDEO_MODEL_DEFAULT` (default: Seedance 2.0 Fast id — cheap iteration,
  native audio per approver ruling 1),
  `ASSET_VIDEO_MODEL_AUDIO` (default: SAME Seedance 2.0 Fast id — override seam
  only; Veo 3.1 is the documented alternative),
  `ASSET_VIDEO_MAX_COST_USD` (default 5.00 — an 8s fast-tier clip ≈ $0.18/attempt;
  the cap leaves headroom for pro-tier one-offs),
  `ASSET_VIDEO_QA_FRAMES` (default 10).
- Rule 13 wording: already says "visual assets"; add one line naming the video
  knobs and the visual-only QA limitation.

## Waves (each gated)
1. `judge_video` + frame sampler + tests (mocked extractor + local-ffmpeg
   integration test + live judge smoke on an ffmpeg-synthesized color clip —
   judge spend only, ~$0.03, no generation spend).
2. Skill video branch + ASSET_VIDEO_* keys + Rule 13 line.
3. Dashboard rows (mockup first) + docs (INSTALL/README/prompt templates).
Generation-side live proof = first real request in a fresh session (same protocol
as images), budget-capped by ASSET_VIDEO_MAX_COST_USD.

## Non-goals
- Audio-track QA (follow-up spec; visual-only limitation recorded per-run).
- Editing/post-production (cutting, captioning) — generation + QA only.
- Streaming/long-form; clips are short-form assets (seconds, not minutes).

## Open questions for the approver
1. Defaults: Seedance 2.0 Fast for iteration, Veo 3.1 when audio is required?
   **Recommend: yes** (cheapest credible iterate; cheapest native-audio).
2. `ASSET_VIDEO_MAX_COST_USD` default **5.00**?
3. QA frame count default **10** per judge call?
4. Audio QA deferred to its own spec (visual-only now)? **Recommend: yes.**
