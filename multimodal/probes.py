"""Backend probes (v0.8). Presence checks only, short timeouts, no downloads."""
from __future__ import annotations

import shutil
import urllib.request


def probe_tesseract() -> dict:
    path = shutil.which("tesseract")
    if path:
        return {"present": True, "backend": "tesseract", "path": path}
    return {"present": False, "backend": "none",
            "status": "NOT_INSTALLED"}


def probe_image_endpoint(timeout_s: int = 3) -> dict:
    """ComfyUI (:8188), A1111/SD WebUI (:7860), or compatible endpoints."""
    for url, name in (("http://127.0.0.1:8188/", "comfyui"),
                      ("http://127.0.0.1:7860/", "a1111-sdwebui")):
        try:
            urllib.request.urlopen(url, timeout=timeout_s)
            return {"present": True, "backend": name, "url": url}
        except Exception:
            continue
    return {"present": False, "backend": "none",
            "status": "PROVIDER_REQUIRED"}


def probe_sapi_voices(timeout_s: int = 30) -> dict:
    """Installed Windows SAPI voices (no synthesis, list only)."""
    try:
        import subprocess
        p = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Add-Type -AssemblyName System.Speech; "
             "(New-Object System.Speech.Synthesis.SpeechSynthesizer)."
             "GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"],
            capture_output=True, text=True, timeout=timeout_s)
        voices = [v.strip() for v in (p.stdout or "").splitlines() if v.strip()]
        if voices:
            return {"present": True, "backend": "sapi", "voices": voices}
    except Exception:
        pass
    return {"present": False, "backend": "none", "status": "NOT_INSTALLED"}
