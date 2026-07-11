"""Wave 2 — single opt-in LIVE smoke call.

NEVER runs in the default gate (excluded by `addopts = -m 'not live'`). Runs only
via `python -m pytest -q -m live`, and only when OPENROUTER_API_KEY is set — else
it SKIPS (does not fail). Budget-capped: one call, max_tokens=16, cheapest verified
model, with a hard `cost_usd < 0.01` assertion so a price surprise fails loudly.

Standing rule: re-verify the model slug/price is still live before relying on this.
"""
import os

import pytest

from panel.secrets import load_env

# pytest does not run the CLI's startup path, so load the gitignored .env here —
# otherwise `pytest -m live` silently SKIPS even on a machine with a configured key
# (an exported env var still wins; missing file is still a no-op).
load_env()

pytestmark = pytest.mark.live

SMOKE_MODEL = "deepseek/deepseek-v4-flash"   # cheapest verified slug (2026-07-07): $0.09/$0.18 per 1M
COST_CEILING_USD = 0.01

_needs_key = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set — live smoke skipped",
)


@_needs_key
def test_live_smoke_single_cheap_call():
    from panel.adapters import call_model
    from panel.cost_meter import CostMeter
    from panel.safe_retry import call_with_retry

    # Retry like the real pipeline does: "no content generated" cold starts are
    # transient by contract, and 16 output tokens is no longer enough headroom for
    # routes that spend tokens before emitting content (observed live 2026-07-09).
    result = call_with_retry(lambda: call_model(
        SMOKE_MODEL,
        [{"role": "user", "content": "Reply with exactly the word: ok"}],
        max_tokens=128,
    ))

    # Content came back
    assert isinstance(result.content, str) and result.content.strip()

    # Token budget respected (allow a small provider overshoot)
    if result.tokens_out is not None:
        assert result.tokens_out <= 140, f"tokens_out={result.tokens_out} exceeds budget"

    # Ground-truth cost accounting works end-to-end AND stays under the ceiling
    assert result.cost_usd is not None, "usage.cost missing — accounting path unverified"
    assert result.cost_usd < COST_CEILING_USD, f"cost {result.cost_usd} >= ceiling {COST_CEILING_USD}"

    # The meter reads the same ground truth
    meter = CostMeter(cap_usd=COST_CEILING_USD)
    meter.add(result)
    assert meter.total == result.cost_usd
    assert meter.breached is False


GPT_MODEL = "openai/gpt-5.6-sol"             # flagship 5.6, $5/$30 per 1M (verified 2026-07-09)
GPT_COST_CEILING_USD = 0.15                  # reasoning model — allow output headroom


@_needs_key
def test_live_gpt_accepts_strict_structured_output():
    """Regression smoke for the 2026-07 GPT-drop: send openai/gpt-5.5 the REAL
    plan-expert prompt + strict response_format. Before the fix this was a
    guaranteed 400 ('additionalProperties' required) and the expert vanished.
    Calls call_model directly (no fallback) so a schema regression fails loudly
    here instead of being papered over by the orchestrator's no-RF retry."""
    from panel import orchestrator
    from panel.adapters import call_model

    result = call_model(
        GPT_MODEL,
        [{"role": "system", "content": (orchestrator._PROMPTS / "expert_plan.md").read_text(encoding="utf-8")},
         {"role": "user", "content": "Task: add a --version flag to a small Python CLI. Keep the plan short."}],
        response_format=orchestrator._PLAN_EXPERT_RF,
        max_tokens=3000,
    )

    parsed = orchestrator._parse_loose(result.content) or None
    assert parsed is not None, f"GPT output did not parse as a JSON object: {result.content[:200]!r}"
    for field in ("summary", "recommendation", "plan", "confidence", "findings"):
        assert field in parsed, f"missing schema-enforced field {field!r}"

    assert result.cost_usd is not None, "usage.cost missing — accounting path unverified"
    assert result.cost_usd < GPT_COST_CEILING_USD, \
        f"cost {result.cost_usd} >= ceiling {GPT_COST_CEILING_USD}"


def _tiny_png(rgb=(255, 0, 0), w=4, h=4):
    """Minimal valid PNG, stdlib-only (solid color) — no fixture file needed."""
    import struct
    import zlib

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


@_needs_key
def test_live_asset_qa_judge_pass_and_revise(tmp_path):
    """Asset-pipeline Wave 2 smoke ($0.25 spec budget; actual ~$0.02): the
    cross-family judge PASSes an asset that meets its criteria and REVISEs one
    that doesn't, on the wire. Generator declared as google/* -> judge resolves
    cross-family (openai luna)."""
    from panel.asset_qa import family, judge_asset

    img = tmp_path / "red.png"
    img.write_bytes(_tiny_png(w=64, h=64))   # solid red square (big enough for
                                             # vision preprocessing — 4x4 degrades)

    ok = judge_asset(img, "- image is a single solid red color\n- no text anywhere",
                     "google/nano-banana-2-pro")
    assert family(ok["judge"]) != "google"          # ruling 1 held on a real call
    assert ok["verdict"] == "PASS", f"judge said {ok}"

    bad = judge_asset(img, "- image must be a single solid BLUE color",
                      "google/nano-banana-2-pro")
    assert bad["verdict"] == "REVISE" and bad["defects"], f"judge said {bad}"
    assert ok["cost_usd"] + bad["cost_usd"] < 0.25  # spec wave-2 budget


@_needs_key
@pytest.mark.skipif(not (__import__("shutil").which("ffmpeg")
                         and __import__("shutil").which("ffprobe")),
                    reason="ffmpeg/ffprobe not on PATH")
def test_live_video_qa_judge_on_synthesized_clip(tmp_path):
    """Video-spec Wave 1 smoke (judge spend only, ~$0.03 — the clip is synthesized
    LOCALLY by ffmpeg, no generation cost): the cross-family judge PASSes a clip
    matching its criteria and REVISEs a mismatched one, from timestamped frames."""
    import subprocess

    from panel.asset_qa import family, judge_video

    clip = tmp_path / "red.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi",
                    "-i", "color=c=red:s=320x240:d=2", "-y", str(clip)],
                   check=True, timeout=120)

    ok = judge_video(clip, "- every frame is a single solid red color\n- no text anywhere",
                     "bytedance/seedance-2.0-fast", frames=4)
    assert family(ok["judge"]) != "bytedance"
    assert ok["verdict"] == "PASS", f"judge said {ok}"
    assert ok["audio_qa"] == "not-performed" and ok["frames_judged"] == 4

    bad = judge_video(clip, "- every frame must be a single solid BLUE color",
                      "bytedance/seedance-2.0-fast", frames=4)
    assert bad["verdict"] == "REVISE" and bad["defects"], f"judge said {bad}"


@_needs_key
def test_live_image_attachment_reaches_the_model(tmp_path):
    """Multimodal smoke: prove the attachment content-part shape works on the wire
    (a mocked-only gate is how the strict-schema bug survived to production)."""
    from panel.adapters import call_model
    from panel.attachments import build_parts
    from panel.safe_retry import call_with_retry

    img = tmp_path / "solid.png"
    img.write_bytes(_tiny_png())
    parts = build_parts([img])

    result = call_with_retry(lambda: call_model(
        GPT_MODEL,
        [{"role": "user",
          "content": [{"type": "text",
                       "text": "What single color is this image? Reply with one lowercase word."}]
                     + parts}],
        max_tokens=2000,
    ))
    assert "red" in result.content.lower(), f"unexpected answer: {result.content[:120]!r}"
    assert result.cost_usd is not None and result.cost_usd < GPT_COST_CEILING_USD
