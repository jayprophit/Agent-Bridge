"""Universal multimodal capability fabric (v0.8, provider-neutral)."""
from __future__ import annotations

from multimodal.router import (
    ASSET_3D, AUDIO_GENERATION, IMAGE_EDITING, IMAGE_GENERATION, MODALITIES,
    OCR, STT, TEXT, TTS, VIDEO_INPUT, VIDEO_OUTPUT, VISION, VOICE_AGENT,
    ModalityBackend, ModalityRoute, MultimodalRouter,
    local_backends_from_registries,
)
from multimodal.probes import (
    probe_image_endpoint, probe_sapi_voices, probe_tesseract,
)
from multimodal import ocr as ocr_backend
from multimodal import stt as stt_backend
from multimodal import image_providers

__all__ = [
    "ASSET_3D", "AUDIO_GENERATION", "IMAGE_EDITING", "IMAGE_GENERATION",
    "MODALITIES", "OCR", "STT", "TEXT", "TTS", "VIDEO_INPUT",
    "VIDEO_OUTPUT", "VISION", "VOICE_AGENT",
    "ModalityBackend", "ModalityRoute", "MultimodalRouter",
    "local_backends_from_registries",
    "probe_image_endpoint", "probe_sapi_voices", "probe_tesseract",
    "ocr_backend", "stt_backend", "image_providers",
]
