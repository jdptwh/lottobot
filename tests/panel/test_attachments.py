"""Attachment support — file->content-part mapping, caps, and orchestrator/CLI
threading. All mocked; no network. Shapes verified against OpenRouter docs
2026-07-09 (image_url / file / input_audio parts; text inlined)."""
import base64
import json

import pytest

import panel.orchestrator as orch
from orch_fakes import FakeCallModel, expert_plan, synth
from panel.attachments import MAX_FILE_BYTES, build_part, build_parts

FABLE = "anthropic/claude-fable-5"
GPT = "openai/gpt-5.5"
OPUS = "anthropic/claude-opus-4.8"
LINEUP = [FABLE, GPT]

PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20


# ---- part shapes ---------------------------------------------------------------

def test_png_becomes_image_url_data_uri(tmp_path):
    p = tmp_path / "shot.png"
    p.write_bytes(PNG_MAGIC)
    part = build_part(p)
    assert part["type"] == "image_url"
    url = part["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == PNG_MAGIC


def test_jpg_and_webp_mime_types(tmp_path):
    for ext, mime in (("jpg", "image/jpeg"), ("webp", "image/webp")):
        p = tmp_path / f"x.{ext}"
        p.write_bytes(b"\xff\xd8fake")
        assert build_part(p)["image_url"]["url"].startswith(f"data:{mime};base64,")


def test_pdf_becomes_file_part_with_filename(tmp_path):
    p = tmp_path / "spec.pdf"
    p.write_bytes(b"%PDF-1.7 fake")
    part = build_part(p)
    assert part["type"] == "file"
    assert part["file"]["filename"] == "spec.pdf"
    assert part["file"]["file_data"].startswith("data:application/pdf;base64,")


def test_audio_becomes_input_audio(tmp_path):
    p = tmp_path / "note.wav"
    p.write_bytes(b"RIFFfake")
    part = build_part(p)
    assert part["type"] == "input_audio"
    assert part["input_audio"]["format"] == "wav"


def test_text_file_inlined_with_banner(tmp_path):
    p = tmp_path / "routing.md"
    p.write_text("# Rules\nRule 12 applies.", encoding="utf-8")
    part = build_part(p)
    assert part["type"] == "text"
    assert "ATTACHED FILE: routing.md" in part["text"]
    assert "Rule 12 applies." in part["text"]


def test_unknown_binary_rejected_with_supported_list(tmp_path):
    p = tmp_path / "blob.bin"
    p.write_bytes(bytes(range(256)) * 4)
    with pytest.raises(ValueError, match="unsupported attachment type.*blob.bin"):
        build_part(p)


def test_oversized_image_rejected(tmp_path):
    p = tmp_path / "huge.png"
    p.write_bytes(b"\x00" * (MAX_FILE_BYTES + 1))
    with pytest.raises(ValueError, match="too large"):
        build_part(p)


def test_missing_file_rejected(tmp_path):
    with pytest.raises(ValueError, match="cannot read attachment"):
        build_part(tmp_path / "nope.png")


# ---- orchestrator threading ------------------------------------------------------

def _fake():
    return FakeCallModel({FABLE: (expert_plan(), 0.001), GPT: (expert_plan(), 0.001),
                          OPUS: (synth(), 0.002)})


def _image_part():
    return {"type": "image_url",
            "image_url": {"url": "data:image/png;base64," + base64.b64encode(PNG_MAGIC).decode()}}


def test_attachments_reach_every_expert_but_not_synth():
    fake = _fake()
    orch.run_plan("t", "look at the mockup", LINEUP, OPUS, call_model=fake, seed=1,
                  attachments=[_image_part()])
    for call in fake.calls:
        user = next(m for m in call["messages"] if m["role"] == "user")
        if call["model"] == OPUS:                      # synthesizer: text only
            assert isinstance(user["content"], str)
        else:                                          # experts: text part + image part
            assert isinstance(user["content"], list)
            assert user["content"][0] == {"type": "text", "text": "look at the mockup"}
            assert user["content"][1]["type"] == "image_url"


def test_no_attachments_keeps_plain_string_content():
    fake = _fake()
    orch.run_plan("t", "plain", LINEUP, OPUS, call_model=fake, seed=1)
    for call in fake.calls:
        user = next(m for m in call["messages"] if m["role"] == "user")
        assert isinstance(user["content"], str)


def test_review_gate_threads_attachments_too():
    from orch_fakes import expert_review
    fake = FakeCallModel({FABLE: (expert_review(), 0.001), GPT: (expert_review(), 0.001)})
    orch.run_review("t", "review this diff", LINEUP, OPUS, call_model=fake, seed=1,
                    attachments=[_image_part()])
    for call in fake.calls:
        user = next(m for m in call["messages"] if m["role"] == "user")
        assert isinstance(user["content"], list) and user["content"][1]["type"] == "image_url"


# ---- CLI wiring -------------------------------------------------------------------

def test_cli_attach_flag_flows_to_experts(tmp_path, monkeypatch):
    from panel import cli
    img = tmp_path / "mock.png"
    img.write_bytes(PNG_MAGIC)
    cfg = tmp_path / "agent.config"
    cfg.write_text('PANEL_ENABLED="1"\n'
                   f'PANEL_VERDICT_PATH="{(tmp_path / "v.json").as_posix()}"\n', encoding="utf-8")
    fake = FakeCallModel({
        "anthropic/claude-fable-5": (expert_plan(), 0.001),
        "openai/gpt-5.6-sol": (expert_plan(), 0.001),
        "anthropic/claude-opus-4.8": (synth(), 0.002),
    })
    code = cli.main(["plan", "check the mockup", "--task-id", "t1",
                     "--config", str(cfg), "--attach", str(img)], call_model=fake)
    assert code == 0
    expert_calls = [c for c in fake.calls if c["model"] != "anthropic/claude-opus-4.8"]
    assert expert_calls and all(isinstance(
        next(m for m in c["messages"] if m["role"] == "user")["content"], list)
        for c in expert_calls)
    assert json.loads((tmp_path / "v.json").read_text())["verdict"] == "PASS"


def test_cli_bad_attachment_exits_2_without_calling_models(tmp_path):
    from panel import cli
    bad = tmp_path / "blob.bin"
    bad.write_bytes(bytes(range(256)) * 4)
    cfg = tmp_path / "agent.config"
    cfg.write_text('PANEL_ENABLED="1"\n', encoding="utf-8")
    fake = FakeCallModel({})
    code = cli.main(["plan", "x", "--task-id", "t1", "--config", str(cfg),
                     "--attach", str(bad)], call_model=fake)
    assert code == 2
    assert fake.calls == []
