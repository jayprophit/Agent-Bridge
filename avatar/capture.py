"""Guided camera capture + photo-to-avatar contracts (v0.8, convergence).

Camera/video is INPUT ONLY for deriving avatar data. Default lifecycle:

  capture -> analyze frames -> derive geometry/appearance data
  -> build avatar profile/assets -> discard raw temporary capture.

Raw captures are EPHEMERAL_RAW_CAPTURE by default and deleted after
derivation (DELETE_AFTER_DERIVATION) unless the user explicitly opts
into retention. Nothing is uploaded anywhere by default; avatar data
stays local unless the user selects another destination.

No photorealistic 3D reconstruction is faked: without a reconstruction
backend, PHOTO_TO_REALISTIC_3D = PROVIDER_REQUIRED, but guided capture,
lifecycle, UI state machine and provider interface work.
"""
from __future__ import annotations

import os
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

# Guided capture views in order.
FRONT = "front"
HEAD_LEFT = "head_left"
HEAD_RIGHT = "head_right"
HEAD_UP = "head_up"
HEAD_DOWN = "head_down"
LEFT_PROFILE = "left_profile"
RIGHT_PROFILE = "right_profile"
OPTIONAL_VIEWS = ("rear", "full_body", "hands")

REQUIRED_VIEWS = (FRONT, HEAD_LEFT, HEAD_RIGHT, HEAD_UP, HEAD_DOWN,
                  LEFT_PROFILE, RIGHT_PROFILE)

# Capture data lifecycle markers.
EPHEMERAL_RAW_CAPTURE = "EPHEMERAL_RAW_CAPTURE"
DERIVED_LANDMARKS = "DERIVED_LANDMARKS"
DERIVED_APPEARANCE_PROFILE = "DERIVED_APPEARANCE_PROFILE"
GENERATED_AVATAR_ASSET = "GENERATED_AVATAR_ASSET"

DELETE_AFTER_DERIVATION = "DELETE_AFTER_DERIVATION"
RETAIN_EXPLICIT = "RETAIN_EXPLICIT"

# Reconstruction status.
PHOTO_TO_REALISTIC_3D_PROVIDER_REQUIRED = "PROVIDER_REQUIRED"


@dataclass
class CaptureFrame:
    view: str
    path: str
    kind: str = EPHEMERAL_RAW_CAPTURE
    bytes_written: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GuidedCaptureSession:
    session_id: str
    required_views: list[str] = field(default_factory=lambda: list(REQUIRED_VIEWS))
    captured: dict[str, CaptureFrame] = field(default_factory=dict)
    camera_permission: bool = False
    retention: str = DELETE_AFTER_DERIVATION
    status: str = "READY"  # READY | CAPTURING | COMPLETE | DERIVED | DISCARDED
    audit: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["captured"] = {k: v.to_dict() for k, v in self.captured.items()}
        return d

    def next_view(self) -> str | None:
        for v in self.required_views:
            if v not in self.captured:
                return v
        return None

    def progress(self) -> dict[str, Any]:
        nxt = self.next_view()
        return {"captured": len(self.captured),
                "required": len(self.required_views),
                "next": nxt or "",
                "complete": nxt is None}


def _write_fixture_frame(path: str, view: str) -> int:
    # Deterministic stand-in bytes for a captured frame (tests/fixtures).
    # A real camera adapter would write actual pixels here.
    data = f"AB-CAPTURE-FIXTURE view={view}\n".encode() * 64
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def capture_view(session: GuidedCaptureSession, view: str,
                 workdir: str) -> CaptureFrame:
    """Capture one guided view. Requires camera permission; writes an
    ephemeral raw frame into workdir and advances the state machine."""
    if not session.camera_permission:
        raise PermissionError("camera permission required")
    if view not in session.required_views and view not in OPTIONAL_VIEWS:
        raise ValueError(f"unknown capture view: {view!r}")
    if view in session.captured:
        raise ValueError(f"view already captured: {view!r}")
    os.makedirs(workdir, exist_ok=True)
    path = os.path.join(workdir, f"raw_{view}_{uuid.uuid4().hex[:8]}.bin")
    n = _write_fixture_frame(path, view)
    frame = CaptureFrame(view=view, path=path, bytes_written=n)
    session.captured[view] = frame
    session.status = "COMPLETE" if session.next_view() is None else "CAPTURING"
    session.audit.append(f"captured:{view}")
    return frame


def derive_from_capture(session: GuidedCaptureSession) -> dict[str, Any]:
    """Analyze frames -> derived data. Deterministic fixture derivation
    (no real CV backend here); values are marked ESTIMATED_FIXTURE."""
    if session.next_view() is not None:
        raise ValueError("capture incomplete")
    landmarks = {v: {"points": 68, "box": [0, 0, 64, 64],
                     "origin": DERIVED_LANDMARKS}
                 for v in session.captured}
    appearance = {"skin_tone": "medium(ESTIMATED_FIXTURE)",
                  "hair_style": "short(ESTIMATED_FIXTURE)",
                  "origin": DERIVED_APPEARANCE_PROFILE}
    asset = {"asset": GENERATED_AVATAR_ASSET, "format": "profile",
             "photorealistic": False,
             "note": "geometry from photos needs a reconstruction provider"}
    session.status = "DERIVED"
    session.audit.append("derived:landmarks+appearance")
    return {"landmarks": landmarks, "appearance": appearance, "asset": asset}


def discard_raw(session: GuidedCaptureSession) -> dict[str, Any]:
    """Delete ephemeral raw frames. Default path after derivation."""
    removed, missing = 0, 0
    for view in list(session.captured):
        frame = session.captured.pop(view)
        try:
            if os.path.exists(frame.path):
                os.remove(frame.path)
                removed += 1
            else:
                missing += 1
        except OSError:
            missing += 1
    session.status = "DISCARDED"
    session.audit.append(f"discarded:removed={removed},missing={missing}")
    return {"removed": removed, "missing": missing}


def finalize_capture(session: GuidedCaptureSession) -> dict[str, Any]:
    """Derive then apply the retention policy (delete by default)."""
    derived = derive_from_capture(session)
    disposition = {"retention": session.retention}
    if session.retention == DELETE_AFTER_DERIVATION:
        disposition.update(discard_raw(session))
    else:
        kept = [f.path for f in session.captured.values()]
        disposition.update({"removed": 0, "kept": kept})
        session.audit.append(f"retained-explicit:{len(kept)}")
    return {"derived": derived, "disposition": disposition,
            "audit": list(session.audit)}


def upload_photo_reference(path: str) -> dict[str, Any]:
    """Photo upload as input/reference contract. Validates a local image
    path; stores nothing remotely. Returns a reference id for the creator."""
    if not isinstance(path, str) or not path:
        raise ValueError("bad photo path")
    if not os.path.exists(path):
        raise FileNotFoundError(f"photo not found: {path!r}")
    if os.path.splitext(path)[1].lower() not in (
            ".png", ".jpg", ".jpeg", ".bmp", ".webp"):
        raise ValueError("unsupported photo format")
    return {"ok": True, "reference": f"photo:{os.path.basename(path)}",
            "kind": EPHEMERAL_RAW_CAPTURE,
            "note": "input only; derive then discard by default"}


class PhotoTo3DProvider:
    """Standard reconstruction provider contract. No local backend here."""

    def __init__(self, backend: str = "none"):
        self.backend = backend

    def status(self) -> dict[str, Any]:
        if self.backend == "none":
            return {"status": PHOTO_TO_REALISTIC_3D_PROVIDER_REQUIRED,
                    "backend": "none",
                    "detail": "no reconstruction backend installed"}
        return {"status": "AVAILABLE", "backend": self.backend}

    def reconstruct(self, reference: str) -> dict[str, Any]:
        st = self.status()
        if st["status"] != "AVAILABLE":
            return {"ok": False, "status": st["status"],
                    "detail": "photorealistic reconstruction needs a provider"}
        return {"ok": True, "asset": f"reconstructed:{reference}"}
