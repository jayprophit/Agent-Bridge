"""STT canonical interface + Whisper-compatible adapter contract (v0.8, Part 4).

Canonical tools: stt.list_backends, stt.status, stt.transcribe_file,
stt.start_stream, stt.stop_stream, stt.languages. No backend is bundled;
an unknown compatible provider plugs in via WhisperCompatibleAdapter.
If none exists locally: WHISPER_BACKEND = NOT_INSTALLED (acceptable).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

WHISPER_BACKEND = "NOT_INSTALLED"


@dataclass
class TranscriptionResult:
    """Canonical transcription envelope."""
    ok: bool = False
    text: str = ""
    language: str = ""
    segments: list[dict[str, Any]] = field(default_factory=list)
    source_artifact: str = ""
    provenance: str = ""
    status: str = "NOT_INSTALLED"
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class STTBackend:
    """Canonical STT backend contract."""

    backend_id: str = "base"

    def list_backends(self) -> list[dict[str, Any]]:
        return []

    def status(self) -> dict[str, Any]:
        return {"backend": self.backend_id, "status": "NOT_INSTALLED"}

    def languages(self) -> list[str]:
        return []

    def transcribe_file(self, audio_path: str, language: str = "") -> TranscriptionResult:
        return TranscriptionResult(status="NOT_INSTALLED",
                                   error="no STT backend installed")

    def start_stream(self, language: str = "") -> dict[str, Any]:
        return {"ok": False, "status": "NOT_INSTALLED"}

    def stop_stream(self, stream_id: str) -> dict[str, Any]:
        return {"ok": False, "status": "NOT_INSTALLED"}


class WhisperCompatibleAdapter(STTBackend):
    """Plugin contract for Whisper-compatible systems.

    Implementation targets (not requirements): whisper.cpp HTTP service,
    faster-whisper HTTP service, OpenAI Whisper API, any compatible local
    HTTP service exposing POST /v1/audio/transcriptions with multipart
    'file' (+ optional 'language') returning JSON with a 'text' field.
    Unknown compatible providers plug in here without bridge changes.
    """

    backend_id = "whisper-compatible"

    def __init__(self, endpoint: str = "", api_key: str = ""):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key  # never logged; pass explicitly, never stored in tree

    def status(self) -> dict[str, Any]:
        if not self.endpoint:
            return {"backend": self.backend_id, "status": "NOT_INSTALLED",
                    "reason": "no endpoint configured"}
        try:
            import urllib.request
            urllib.request.urlopen(self.endpoint.rstrip("/") + "/", timeout=3)
            return {"backend": self.backend_id, "status": "AVAILABLE",
                    "endpoint": self.endpoint}
        except Exception as e:  # noqa: BLE001
            return {"backend": self.backend_id, "status": "NOT_INSTALLED",
                    "reason": str(e)[:200]}

    def transcribe_file(self, audio_path: str, language: str = "") -> TranscriptionResult:
        if not self.endpoint:
            return TranscriptionResult(status="NOT_INSTALLED",
                                       error="no endpoint configured")
        try:
            import json
            import urllib.request
            boundary = "----abstt1234"
            with open(audio_path, "rb") as f:
                audio = f.read()
            parts = [
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                f"filename=\"audio.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode(),
                audio,
                f"\r\n--{boundary}--\r\n".encode(),
            ]
            body = b"".join(parts)
            if language:
                body = (f"--{boundary}\r\nContent-Disposition: form-data; "
                        f"name=\"language\"\r\n\r\n{language}\r\n".encode() + body)
            req = urllib.request.Request(
                self.endpoint.rstrip("/") + "/v1/audio/transcriptions",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
            if self.api_key:
                req.add_header("Authorization", f"Bearer {self.api_key}")
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read().decode())
            text = data.get("text", "")
            return TranscriptionResult(
                ok=bool(text), text=text,
                language=language or data.get("language", ""),
                source_artifact=audio_path,
                provenance=f"whisper-compatible ({self.endpoint})",
                status="AVAILABLE" if text else "NOT_INSTALLED")
        except Exception as e:  # noqa: BLE001
            return TranscriptionResult(status="NOT_INSTALLED",
                                       error=str(e)[:200])


def probe_local() -> dict[str, Any]:
    """Any STT backend already present? (No downloads, presence only.)"""
    import shutil
    for exe in ("whisper", "whisper.cpp", "faster-whisper"):
        path = shutil.which(exe)
        if path:
            return {"present": True, "backend": exe, "path": path}
    return {"present": False, "backend": "none", "status": "NOT_INSTALLED"}
