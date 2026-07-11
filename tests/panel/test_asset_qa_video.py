"""Video QA (video spec Wave 1) — frame sampling, one labeled multi-frame judge
call, audio fail-closed, CLI --video. Mocked extractor/prober; one integration
test uses real ffmpeg (skipped where absent)."""
import json
import shutil
import subprocess

import pytest

import panel.asset_qa as aq
from orch_fakes import FakeCallModel

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
GEN = "bytedance/seedance-2.0-fast"          # video generator family: bytedance
LUNA = "openai/gpt-5.6-luna"


def qa_json(verdict="PASS", score=0.9, defects=None, hint=""):
    return {"verdict": verdict, "score": score, "defects": defects or [], "reprompt_hint": hint}


def fake_prober(_):
    return 8.0


def make_fake_extractor(tmp_path):
    def _extract(video, times, out_dir):
        paths = []
        for i, t in enumerate(times):
            p = tmp_path / f"f{i}.png"
            p.write_bytes(PNG)
            paths.append(p)
        return paths
    return _extract


# ---- sampling -----------------------------------------------------------------

def test_sample_times_first_last_and_even_spacing():
    ts = aq.sample_times(8.0, 10)
    assert len(ts) == 10
    assert ts == sorted(ts) and len(set(ts)) == 10
    assert ts[0] < 0.2 and 7.8 < ts[-1] < 8.0


def test_sample_times_clamps_short_clips_and_small_n():
    ts = aq.sample_times(0.4, 2)
    assert len(ts) == 2 and 0 < ts[0] < ts[-1] < 0.4
    assert len(aq.sample_times(5.0, 1)) == 2      # n floors at 2 (first+last)


# ---- judge_video ----------------------------------------------------------------

def test_judge_video_labels_every_frame_with_timestamp(tmp_path):
    fake = FakeCallModel({LUNA: (qa_json(), 0.01)})
    out = aq.judge_video("clip.mp4", "solid red throughout", GEN, frames=4,
                         call_model=fake, prober=fake_prober,
                         extractor=make_fake_extractor(tmp_path))
    assert out["verdict"] == "PASS" and out["frames_judged"] == 4
    assert out["audio_qa"] == "not-performed"
    assert aq.family(out["judge"]) != "bytedance"          # cross-family holds for video
    user = next(m for m in fake.calls[0]["messages"] if m["role"] == "user")
    labels = [c["text"] for c in user["content"] if c["type"] == "text"]
    images = [c for c in user["content"] if c["type"] == "image_url"]
    assert labels[0].startswith("ACCEPTANCE CRITERIA:")
    assert len(images) == 4
    assert sum("frame at t=" in x for x in labels) == 4     # every frame labeled


def test_judge_video_system_prompt_fails_closed_on_audio():
    sys_prompt = aq._JUDGE_SYSTEM_VIDEO
    assert "CANNOT hear audio" in sys_prompt
    assert "fail closed" in sys_prompt.lower()


def test_judge_video_mismatched_extractor_is_loud_error(tmp_path):
    # a custom extractor returning the wrong frame count must not silently mislabel
    def short_extractor(video, times, out_dir):
        return make_fake_extractor(tmp_path)(video, times[:2], out_dir)   # too few
    with pytest.raises(ValueError, match="frames for"):
        aq.judge_video("clip.mp4", "c", GEN, frames=5, call_model=FakeCallModel({}),
                       prober=fake_prober, extractor=short_extractor)


def test_judge_video_missing_ffprobe_is_loud_error(tmp_path):
    def broken_prober(_):
        raise ValueError("ffprobe unavailable — install ffmpeg to QA video")
    with pytest.raises(ValueError, match="ffprobe unavailable"):
        aq.judge_video("clip.mp4", "c", GEN, call_model=FakeCallModel({}),
                       prober=broken_prober)


# ---- CLI --video -----------------------------------------------------------------

def test_cli_video_mode(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(aq, "_probe_duration", fake_prober)
    monkeypatch.setattr(aq, "_ffmpeg_extract",
                        lambda v, t, d: make_fake_extractor(tmp_path)(v, t, d))
    fake = FakeCallModel({LUNA: (qa_json("REVISE", 0.4,
                                         defects=[{"criterion": "c", "problem": "p"}]), 0.01)})
    code = aq.main(["--video", "clip.mp4", "--criteria", "c",
                    "--generator-model", GEN, "--frames", "3"], call_model=fake)
    assert code == 2
    assert json.loads(capsys.readouterr().out)["frames_judged"] == 3


def test_cli_image_and_video_are_mutually_exclusive(tmp_path):
    with pytest.raises(SystemExit):
        aq.main(["--image", "a.png", "--video", "b.mp4", "--criteria", "c",
                 "--generator-model", GEN], call_model=FakeCallModel({}))


# ---- real-ffmpeg integration (skipped where absent) --------------------------------

_has_ffmpeg = shutil.which("ffmpeg") and shutil.which("ffprobe")


@pytest.mark.skipif(not _has_ffmpeg, reason="ffmpeg/ffprobe not on PATH")
def test_real_ffmpeg_probe_and_extract(tmp_path):
    clip = tmp_path / "red.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi",
                    "-i", "color=c=red:s=320x240:d=2", "-y", str(clip)],
                   check=True, timeout=120)
    dur = aq._probe_duration(clip)
    assert 1.5 < dur < 2.5
    frames = aq._ffmpeg_extract(clip, aq.sample_times(dur, 4), tmp_path / "frames")
    assert len(frames) == 4 and all(p.exists() and p.stat().st_size > 500 for p in frames)
