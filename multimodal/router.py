"""Multimodal capability router (v0.8). Provider-neutral modality routing.

Routes TEXT/VISION/OCR/IMAGE_GENERATION/IMAGE_EDITING/TTS/STT/AUDIO tasks to
backends by verified capability — never by model name. Backends: local
deterministic tools, OS engines, vision-model fallback, configured providers.
Absent backends report NOT_INSTALLED/PROVIDER_REQUIRED truthfully.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

TEXT = "TEXT"
VISION = "VISION"
OCR = "OCR"
IMAGE_GENERATION = "IMAGE_GENERATION"
IMAGE_EDITING = "IMAGE_EDITING"
TTS = "TTS"
STT = "STT"
AUDIO_GENERATION = "AUDIO_GENERATION"
VOICE_AGENT = "VOICE_AGENT"
VIDEO_INPUT = "VIDEO_INPUT"
VIDEO_OUTPUT = "VIDEO_OUTPUT"
ASSET_3D = "3D_ASSET"

MODALITIES = (
    TEXT, VISION, OCR, IMAGE_GENERATION, IMAGE_EDITING, TTS, STT,
    AUDIO_GENERATION, VOICE_AGENT, VIDEO_INPUT, VIDEO_OUTPUT, ASSET_3D,
)


@dataclass
class ModalityBackend:
    """One backend serving a modality."""
    backend_id: str
    modality: str
    kind: str  # local_tool | os_engine | vision_model | provider | none
    tool_ids: list[str] = field(default_factory=list)
    verified: bool = False
    evidence: str = ""
    limitation: str = ""


@dataclass
class ModalityRoute:
    modality: str
    backend_id: str = ""
    tool_ids: list[str] = field(default_factory=list)
    status: str = "PROVIDER_REQUIRED"
    reasons: list[str] = field(default_factory=list)


class MultimodalRouter:
    """Routes a modality to the best available backend."""

    def __init__(self, backends: list[ModalityBackend] | None = None):
        self._backends: dict[str, list[ModalityBackend]] = {}
        for b in backends or []:
            self._backends.setdefault(b.modality, []).append(b)

    def register(self, backend: ModalityBackend) -> None:
        self._backends.setdefault(backend.modality, []).append(backend)

    def route(self, modality: str, prefer_local: bool = True) -> ModalityRoute:
        cands = list(self._backends.get(modality, []))
        if not cands:
            return ModalityRoute(modality=modality, reasons=["no backend registered"])
        verified = [b for b in cands if b.verified]
        pool = verified or cands
        if prefer_local:
            local = [b for b in pool if b.kind in ("local_tool", "os_engine", "vision_model")]
            if local:
                pool = local
        best = pool[0]
        status = "AVAILABLE" if best.verified else (
            "NOT_INSTALLED" if best.kind == "none" else "PROVIDER_REQUIRED")
        return ModalityRoute(modality=modality, backend_id=best.backend_id,
                             tool_ids=list(best.tool_ids), status=status,
                             reasons=[best.evidence or best.limitation or best.kind])


def local_backends_from_registries(tool_registry=None, model_registry=None) -> list[ModalityBackend]:
    """Build backend list from live registries (no probing side effects)."""
    backends: list[ModalityBackend] = [
        ModalityBackend("bridge-text", TEXT, "local_tool", ["tools.list"],
                        True, "core text path"),
    ]
    if tool_registry is not None:
        try:
            ids = set(tool_registry.ids())
        except Exception:
            ids = set()
        det_image = sorted(i for i in ids if i.startswith("image.") and i in (
            "image.resize", "image.crop", "image.convert", "image.diagram",
            "image.annotate", "image.compose"))
        if det_image:
            backends.append(ModalityBackend(
                "bridge-image-deterministic", IMAGE_GENERATION, "local_tool",
                det_image, True, "stdlib deterministic ops (not generative)"))
        if "image.generate" in ids:
            backends.append(ModalityBackend(
                "image-generative", IMAGE_GENERATION, "provider",
                ["image.generate", "image.edit", "image.enhance"],
                False, "",
                "no local image endpoint configured (ComfyUI/A1111/compatible)"))
        if "speech.tts" in ids:
            backends.append(ModalityBackend(
                "os-sapi-tts", TTS, "os_engine", ["speech.tts"],
                False, "", "System.Speech voices present; synthesis E2E pending"))
        if "speech.stt" in ids:
            backends.append(ModalityBackend(
                "stt-slot", STT, "none", ["speech.stt"],
                False, "", "no STT backend installed"))
        if "vision.inspect_image" in ids:
            backends.append(ModalityBackend(
                "vision-slot", VISION, "none", ["vision.inspect_image"],
                False, "", "no verified vision model"))
        ocr_tools = sorted(i for i in ids if i.startswith(("vision.detect_text", "vision.ocr", "ocr.")))
        if ocr_tools:
            backends.append(ModalityBackend(
                "ocr-slot", OCR, "none", ocr_tools,
                False, "", "no OCR engine installed"))
    if model_registry is not None:
        try:
            vision_models = [m.model_id for m in model_registry.vision_models()]
        except Exception:
            vision_models = []
        if vision_models:
            backends.append(ModalityBackend(
                "vision-model-fallback", VISION, "vision_model", [],
                False, "",
                f"provider-advertised vision models exist ({len(vision_models)}); none verified"))
    # OS-native OCR backend (presence-checked, no downloads).
    try:
        from multimodal.ocr import is_available as _ocr_available
        ocr = _ocr_available()
        if ocr.get("present"):
            backends.append(ModalityBackend(
                "windows-ocr", OCR, "os_engine", ["vision.detect_text"],
                True, f"Windows OCR ({ocr.get('language', '?')}), fixture-verified"))
    except Exception:
        pass
    return backends
