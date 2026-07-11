"""panel/asset_qa.py — asset QA judge + loop bookkeeping (asset pipeline Wave 1).

Judges a generated asset (image) against explicit acceptance criteria using a
multimodal model, and provides the bounded-loop bookkeeping the asset-forge skill
(Wave 2) drives: attempt tracking, budget enforcement, best-candidate selection,
and the escalate-to-panel flag on exhaustion (spec ruling 2: exhausted loops go to
panel review then manual approval — never auto-accept, never silent-stop).

Spec ruling 1: the judge is CROSS-FAMILY by design — `pick_judge` refuses to score
a generator's output with a judge from the same provider family (style bias).

Reuses the panel's proven plumbing: adapters.call_model (cost truth), attachments
(image -> content part), orchestrator._call_structured (strict schema + 400
fallback) and _parse_loose (tolerant parse). Stdlib only; generation itself is
MCP-side (Wave 2) — this module never calls an image model.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from panel.adapters import call_model as _default_call_model
from panel.attachments import build_part
from panel.errors import PanelError
from panel.orchestrator import _call_structured, _clamp01, _obj, _parse_loose, _rf

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MAX_COST_USD = 1.00
DEFAULT_VIDEO_QA_FRAMES = 10

# Cross-family judge pool, cheapest-first (prices verified 2026-07-09).
JUDGE_POOL = (
    "openai/gpt-5.6-luna",            # $1/$6
    "google/gemini-3.1-flash-lite",   # $0.25/$1.5
    "anthropic/claude-opus-4.8",      # $5/$25 — last resort
)

_STR = {"type": "string"}
_JUDGE_RF = _rf("asset_qa", _obj({
    "verdict": {"type": "string", "enum": ["PASS", "REVISE"]},
    "score": {"type": "number"},
    "defects": {"type": "array",
                "items": _obj({"criterion": _STR, "problem": _STR})},
    "reprompt_hint": _STR,
}))

_JUDGE_SYSTEM = """You are a strict visual QA judge. You are given ONE generated \
asset (attached image) and the acceptance criteria it was generated against. Judge \
ONLY against the stated criteria — do not invent preferences. Be adversarial: pass \
only what genuinely satisfies every criterion. Verify each criterion by LOOKING at \
the attached image; if you cannot clearly confirm a criterion from the image itself, \
that criterion FAILS (fail closed — never assume).

Return a single JSON object with exactly these fields:
- "verdict": "PASS" | "REVISE"
- "score": number 0.0-1.0 — overall fitness against the criteria.
- "defects": array of {"criterion": string, "problem": string} — each criterion \
that is not met and what exactly is wrong (empty when verdict is PASS).
- "reprompt_hint": string — one or two sentences a generator can act on to fix \
the defects ("" when verdict is PASS)."""


def family(slug):
    """Provider family of an OpenRouter slug ('openai/gpt-...' -> 'openai')."""
    return str(slug).split("/", 1)[0].lower()


def pick_judge(generator_model, preferred=None, pool=JUDGE_POOL):
    """Cross-family judge for a generator (spec ruling 1). A `preferred` judge is
    honored ONLY if it is from a different family than the generator; otherwise
    fall through to the pool. Raises ValueError if no cross-family judge exists."""
    gen_family = family(generator_model)
    if preferred and family(preferred) != gen_family:
        return preferred
    for candidate in pool:
        if family(candidate) != gen_family:
            return candidate
    raise ValueError(f"no cross-family judge available for generator {generator_model!r}")


def _sanitize(raw):
    """Coerce untrusted judge output to the contract shape (same philosophy as the
    orchestrator: unknown values can never poison the loop). `defects` must be an
    actual list — a parseable-but-wrong-typed value like {"defects": 1} would
    TypeError in the comprehension (audit fix)."""
    verdict = raw.get("verdict")
    raw_defects = raw.get("defects")
    defects = [{"criterion": str(d.get("criterion", "")), "problem": str(d.get("problem", ""))}
               for d in (raw_defects if isinstance(raw_defects, list) else [])
               if isinstance(d, dict)]
    if verdict not in ("PASS", "REVISE"):
        verdict = "REVISE"          # fail closed: an unparseable verdict never passes
    if verdict == "PASS" and defects:
        verdict = "REVISE"          # a "PASS with defects" is a contradiction — fail closed
    return {"verdict": verdict, "score": _clamp01(raw.get("score")),
            "defects": defects, "reprompt_hint": str(raw.get("reprompt_hint", ""))}


def judge_asset(image_path, criteria, generator_model, *, judge=None,
                call_model=None, api_key=None, max_tokens=None):
    """Score one asset against its acceptance criteria. Returns
    {verdict, score, defects, reprompt_hint, judge, cost_usd}. Raises ValueError
    (bad attachment / no cross-family judge) or PanelError (provider failure)."""
    call_model = call_model or _default_call_model
    judge_model = pick_judge(generator_model, preferred=judge)
    part = build_part(image_path)
    if part.get("type") != "image_url":
        raise ValueError(f"asset must be an image, got a {part.get('type')} part: {image_path}")
    messages = [
        {"role": "system", "content": _JUDGE_SYSTEM},
        {"role": "user", "content": [
            {"type": "text", "text": "ACCEPTANCE CRITERIA:\n" + criteria},
            part,
        ]},
    ]
    res = _call_structured(call_model, judge_model, messages, _JUDGE_RF,
                           max_tokens=max_tokens, api_key=api_key)
    out = _sanitize(_parse_loose(res.content))
    out["judge"] = judge_model
    out["cost_usd"] = res.cost_usd if res.cost_usd is not None else 0.0
    return out


_JUDGE_SYSTEM_VIDEO = """You are a strict visual QA judge for a GENERATED VIDEO. \
You are given sampled frames from the video, each labeled with its timestamp, plus \
the acceptance criteria the video was generated against. Judge ONLY against the \
stated criteria, using the frame sequence for temporal criteria (order, timing, \
continuity). Be adversarial: pass only what every frame-verifiable criterion \
genuinely satisfies. You CANNOT hear audio: any criterion about sound, music, \
narration, or dialogue is unverifiable from frames — mark it as a defect \
(fail closed) with problem "audio cannot be verified from frames". If you cannot \
clearly confirm a criterion from the frames themselves, that criterion FAILS.

Return a single JSON object with exactly these fields:
- "verdict": "PASS" | "REVISE"
- "score": number 0.0-1.0 — overall fitness against the criteria.
- "defects": array of {"criterion": string, "problem": string} — each criterion \
that is not met and what exactly is wrong (empty when verdict is PASS).
- "reprompt_hint": string — one or two sentences a video generator can act on to \
fix the defects ("" when verdict is PASS)."""


def _probe_duration(video_path):
    """Video duration in seconds via ffprobe. Raises ValueError when ffprobe is
    missing or the file is unreadable — fail loud before any judge spend."""
    import subprocess
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ValueError(f"ffprobe unavailable ({e}) — install ffmpeg to QA video") from e
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise ValueError(f"could not probe duration of {video_path}: "
                         f"{(r.stderr or r.stdout).strip()[:200]}") from None


def _ffmpeg_extract(video_path, times, out_dir):
    """Default frame extractor: one JPEG per timestamp. Returns list of Paths."""
    import subprocess
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, t in enumerate(times):
        out = out_dir / f"frame_{i:02d}_t{t:.2f}.jpg"
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video_path),
             "-frames:v", "1", "-q:v", "3", "-y", str(out)],
            capture_output=True, text=True, timeout=120)
        if r.returncode != 0 or not out.exists():
            raise ValueError(f"frame extraction failed at t={t:.2f}s: "
                             f"{r.stderr.strip()[:200]}")
        paths.append(out)
    return paths


def sample_times(duration, n):
    """n ascending timestamps: just-after-first, just-before-last, evenly between.
    Clamps sensibly for very short clips."""
    n = max(2, int(n))
    duration = max(float(duration), 0.2)
    eps = min(0.1, duration / 20.0)
    first, last = eps, duration - eps
    if n == 2:
        return [first, last]
    step = (last - first) / (n - 1)
    return [first + i * step for i in range(n)]


def judge_video(video_path, criteria, generator_model, *, judge=None,
                frames=DEFAULT_VIDEO_QA_FRAMES, call_model=None, api_key=None,
                max_tokens=None, extractor=None, prober=None, workdir=None):
    """Score one generated VIDEO against its acceptance criteria by judging a
    timestamp-labeled sample of frames in ONE cross-family judge call. Visual
    track only (spec ruling 4): audio criteria fail closed. Returns the same
    shape as judge_asset plus frames_judged and audio_qa."""
    import tempfile
    call_model = call_model or _default_call_model
    judge_model = pick_judge(generator_model, preferred=judge)
    prober = prober or _probe_duration
    extractor = extractor or _ffmpeg_extract
    times = sample_times(prober(video_path), frames)
    with tempfile.TemporaryDirectory() as td:
        frame_paths = extractor(video_path, times, workdir or td)
        # Guard against a mismatched extractor: a silent zip truncation would
        # mislabel frames with the wrong timestamps (audit minor).
        if len(frame_paths) != len(times):
            raise ValueError(f"extractor returned {len(frame_paths)} frames for "
                             f"{len(times)} sampled timestamps")
        content = [{"type": "text", "text": "ACCEPTANCE CRITERIA:\n" + criteria}]
        for t, fp in zip(times, frame_paths):
            content.append({"type": "text", "text": f"frame at t={t:.2f}s:"})
            part = build_part(fp)
            if part.get("type") != "image_url":
                raise ValueError(f"extractor produced a non-image frame: {fp}")
            content.append(part)
        messages = [{"role": "system", "content": _JUDGE_SYSTEM_VIDEO},
                    {"role": "user", "content": content}]
        res = _call_structured(call_model, judge_model, messages, _JUDGE_RF,
                               max_tokens=max_tokens, api_key=api_key)
    out = _sanitize(_parse_loose(res.content))
    # CODE-enforced audio fail-closed (spec ruling 4): the system prompt tells the
    # judge audio is unverifiable, but an instruction to an untrusted model is not
    # an invariant. If the criteria mention audio and the judge PASSed without an
    # audio defect, downgrade here. Keyword heuristic (English) — imperfect, but
    # strictly safer than trusting the judge; the sidecar records audio_qa anyway.
    audio_terms = ("audio", "sound", "music", "narration", "dialogue", "voice",
                   "hum", "sfx", "soundtrack")
    lc = criteria.lower()
    if out["verdict"] == "PASS" and any(t in lc for t in audio_terms) \
            and not any("audio" in d["problem"].lower() or "audio" in d["criterion"].lower()
                        for d in out["defects"]):
        out["verdict"] = "REVISE"
        out["defects"].append({"criterion": "audio criteria present",
                               "problem": "audio cannot be verified from frames — human ears required"})
    out["judge"] = judge_model
    out["cost_usd"] = res.cost_usd if res.cost_usd is not None else 0.0
    out["frames_judged"] = len(frame_paths)
    out["audio_qa"] = "not-performed"      # visual track only — spec ruling 4
    return out


class ForgeLoop:
    """Bounded generate->judge loop bookkeeping (the skill drives generation).

    Usage per attempt: check `should_continue()`, generate, `record(...)` the
    judged attempt. `result()` yields the final state:
      status: "PASS" (a passing attempt exists) or "EXHAUSTED" (attempts/budget
      spent) — EXHAUSTED always sets escalate_to_panel=True (spec ruling 2).
      best: the highest-scoring attempt either way (never silently discarded).
    """

    def __init__(self, criteria, *, max_attempts=DEFAULT_MAX_ATTEMPTS,
                 max_cost_usd=DEFAULT_MAX_COST_USD):
        self.criteria = criteria
        self.max_attempts = max(1, int(max_attempts))
        self.max_cost_usd = float(max_cost_usd)
        self.attempts = []

    @property
    def cost_total(self):
        return sum(a["cost_usd"] for a in self.attempts)

    @property
    def passed(self):
        return any(a["qa"]["verdict"] == "PASS" for a in self.attempts)

    def should_continue(self):
        return (not self.passed
                and len(self.attempts) < self.max_attempts
                and self.cost_total < self.max_cost_usd)

    def record(self, image_path, prompt, qa, *, gen_cost_usd=0.0):
        """Record one judged attempt. `qa` is judge_asset()'s dict; gen_cost_usd is
        the generation-side spend the caller knows (MCP side), 0 if unknown."""
        self.attempts.append({
            "n": len(self.attempts) + 1, "image": str(image_path), "prompt": str(prompt),
            "qa": qa, "cost_usd": float(qa.get("cost_usd", 0.0)) + float(gen_cost_usd),
        })

    def next_prompt(self, base_prompt):
        """Fold the latest attempt's defects + reprompt hint into the next prompt."""
        if not self.attempts:
            return base_prompt
        qa = self.attempts[-1]["qa"]
        notes = "; ".join(f"{d['criterion']}: {d['problem']}" for d in qa["defects"])
        hint = qa.get("reprompt_hint", "")
        return (f"{base_prompt}\n\nPREVIOUS ATTEMPT WAS REJECTED. Fix these defects: "
                f"{notes or 'see hint'}. {hint}").strip()

    def result(self):
        best = max(self.attempts, key=lambda a: a["qa"]["score"], default=None)
        status = "PASS" if self.passed else "EXHAUSTED"
        return {
            "status": status,
            "escalate_to_panel": status == "EXHAUSTED",   # ruling 2: never silent-stop
            "attempts": self.attempts,
            "best": best,
            "cost_usd_total": round(self.cost_total, 10),
            "criteria": self.criteria,
        }


def write_sidecar(asset_path, result):
    """Provenance sidecar next to the asset: <asset>.forge.json."""
    p = Path(str(asset_path) + ".forge.json")
    p.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return p


def main(argv=None, call_model=None):
    """CLI: judge one asset. Exit 0 PASS / 2 REVISE / 3 error. Prints the QA JSON
    to stdout so the asset-forge skill can consume it directly."""
    from panel.secrets import load_env
    load_env()   # judge runs over OpenRouter — pick up the gitignored .env like panel.cli does

    ap = argparse.ArgumentParser(prog="panel.asset_qa",
                                 description="QA-judge a generated asset against criteria.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", default=None)
    src.add_argument("--video", default=None,
                     help="judge a VIDEO via timestamp-labeled frame sampling "
                          "(visual track only; audio criteria fail closed)")
    ap.add_argument("--criteria", default=None, help="inline acceptance criteria")
    ap.add_argument("--criteria-file", default=None)
    ap.add_argument("--generator-model", required=True,
                    help="slug that generated the asset (judge must be cross-family)")
    ap.add_argument("--judge", default=None, help="judge slug override (still cross-family)")
    ap.add_argument("--frames", type=int, default=DEFAULT_VIDEO_QA_FRAMES,
                    help="frames sampled per video judgement")
    args = ap.parse_args(argv)

    criteria = (Path(args.criteria_file).read_text(encoding="utf-8")
                if args.criteria_file else (args.criteria or ""))
    if not criteria.strip():
        print("[asset_qa] error: no acceptance criteria (--criteria or --criteria-file)",
              file=sys.stderr)
        return 3
    try:
        if args.video:
            qa = judge_video(args.video, criteria, args.generator_model,
                             judge=args.judge, frames=args.frames, call_model=call_model)
        else:
            qa = judge_asset(args.image, criteria, args.generator_model,
                             judge=args.judge, call_model=call_model)
    except (ValueError, PanelError) as e:
        print(f"[asset_qa] error: {e}", file=sys.stderr)
        return 3
    print(json.dumps(qa, indent=2))
    return 0 if qa["verdict"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
