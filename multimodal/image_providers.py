"""Image provider discovery + generation/edit contracts (v0.8, Part 6).

Provider-neutral contracts for ComfyUI-compatible, SD WebUI/A1111-compatible,
and generic compatible image endpoints. Discovery only; no downloads, no
bundled models. Absent backends stay PROVIDER_REQUIRED.
"""
from __future__ import annotations

import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class GenerationRequest:
    """Canonical image-generation contract."""
    prompt: str
    negative_prompt: str = ""
    width: int = 512
    height: int = 512
    seed: int = -1
    provider: str = ""
    model: str = ""
    reference_image: str = ""  # artifact ref, where supported

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EditRequest:
    """Canonical image-edit contract (provenance preserved)."""
    source_artifact: str
    instruction: str
    mask_artifact: str = ""
    reference_images: list[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    seed: int = -1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ImageEndpoint:
    """A discovered/configured compatible image endpoint."""
    endpoint_id: str  # comfyui | a1111 | generic
    url: str
    reachable: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def discover(timeout_s: int = 3) -> list[ImageEndpoint]:
    """Probe well-known local endpoints (presence only, never installs)."""
    found = []
    for endpoint_id, url in (
        ("comfyui", "http://127.0.0.1:8188/"),
        ("a1111", "http://127.0.0.1:7860/"),
    ):
        reachable, note = False, ""
        try:
            urllib.request.urlopen(url, timeout=timeout_s)
            reachable, note = True, "reachable"
        except Exception as e:  # noqa: BLE001
            note = f"{type(e).__name__}"
        found.append(ImageEndpoint(endpoint_id, url, reachable, note))
    return found


class CompatibleImageAdapter:
    """Adapter contract for a configured compatible endpoint.

    Concrete providers implement generate()/edit() against their own HTTP
    API and return ArtifactRegistry-style references with provenance.
    """

    def __init__(self, endpoint: ImageEndpoint):
        self.endpoint = endpoint

    def generate(self, request: GenerationRequest) -> dict[str, Any]:
        raise NotImplementedError("provider-specific generate()")

    def edit(self, request: EditRequest) -> dict[str, Any]:
        raise NotImplementedError("provider-specific edit()")
