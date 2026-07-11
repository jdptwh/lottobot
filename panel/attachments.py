"""Attachment loading — local files become chat-completion content parts.

Maps a file path to the OpenRouter (OpenAI-compatible) multimodal content part
for its type (verified against OpenRouter docs 2026-07-09):

  * images (.png .jpg .jpeg .webp .gif)  -> {"type":"image_url", ...} data URI
  * PDF (.pdf)                           -> {"type":"file", ...} data URI
                                            (OpenRouter file-parser: native engine
                                            when the model supports it, else OCR)
  * audio (.wav .mp3)                    -> {"type":"input_audio", ...}
  * anything UTF-8 decodable             -> {"type":"text", ...} inlined with a
                                            filename banner (cheapest + universal)
  * other binary                         -> ValueError (listed, never silent)

Stdlib only. Size caps fail loudly BEFORE any provider call: base64 inflates by
~33% and oversized requests die at the provider with a per-model error — better
to reject locally with a clear message. Model support varies (an audio part sent
to a text-only model is a provider error); the orchestrator's dropped-expert
reasons + diagnostics make that visible per expert rather than silent.
"""
from __future__ import annotations

import base64
from pathlib import Path

_IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".webp": "image/webp", ".gif": "image/gif"}
_AUDIO_FORMAT = {".wav": "wav", ".mp3": "mp3"}

MAX_FILE_BYTES = 10 * 1024 * 1024      # per attachment (pre-base64)
MAX_TEXT_BYTES = 2 * 1024 * 1024       # per inlined text file
MAX_TOTAL_BYTES = 20 * 1024 * 1024     # whole attachment set (pre-base64)


def _data_uri(mime, data):
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def build_part(path):
    """One file -> one content part. Raises ValueError on unsupported/oversized."""
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError as e:
        raise ValueError(f"cannot read attachment {p}: {e}") from e
    ext = p.suffix.lower()

    if ext in _IMAGE_MIME or ext == ".pdf" or ext in _AUDIO_FORMAT:
        if len(data) > MAX_FILE_BYTES:
            raise ValueError(f"attachment too large: {p.name} is {len(data)} bytes "
                             f"(cap {MAX_FILE_BYTES}); resize/split it")
        if ext in _IMAGE_MIME:
            return {"type": "image_url",
                    "image_url": {"url": _data_uri(_IMAGE_MIME[ext], data)}}
        if ext == ".pdf":
            return {"type": "file",
                    "file": {"filename": p.name,
                             "file_data": _data_uri("application/pdf", data)}}
        return {"type": "input_audio",
                "input_audio": {"data": base64.b64encode(data).decode("ascii"),
                                "format": _AUDIO_FORMAT[ext]}}

    # everything else: inline as text if it decodes, else reject loudly
    if len(data) > MAX_TEXT_BYTES:
        raise ValueError(f"text attachment too large: {p.name} is {len(data)} bytes "
                         f"(cap {MAX_TEXT_BYTES}); trim it or attach an excerpt")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(
            f"unsupported attachment type: {p.name} — supported: images "
            f"({', '.join(sorted(_IMAGE_MIME))}), .pdf, audio "
            f"({', '.join(sorted(_AUDIO_FORMAT))}), or any UTF-8 text file") from None
    return {"type": "text",
            "text": f"===== ATTACHED FILE: {p.name} =====\n{text}\n===== END {p.name} ====="}


def build_parts(paths):
    """All files -> content parts, enforcing the total-size cap. Raises ValueError."""
    total = 0
    parts = []
    for path in paths or []:
        total += Path(path).stat().st_size if Path(path).exists() else 0
        parts.append(build_part(path))
    if total > MAX_TOTAL_BYTES:
        raise ValueError(f"attachments total {total} bytes exceeds cap {MAX_TOTAL_BYTES}; "
                         f"send fewer/smaller files")
    return parts
