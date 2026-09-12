"""Avatar character creator architecture (v0.8, convergence).

Standard avatar customization: presets, customize-from-preset, randomized
generation, image reference, guided capture hooks, and GLTF/GLB/VRM import
contracts. Game-style workflow with SIMPLE and ADVANCED modes.

Honesty contract (do NOT fake geometry):
  PROFILE_SUPPORTED   - value stored in the appearance profile.
  RENDERED_SUPPORTED  - procedural reference GLB actually renders it
                        (Head/Jaw/EyeL/EyeR nodes + named expressions).
  PROVIDER_REQUIRED   - needs a 3D/morph provider (no local backend here).

Appearance, voice, personality and expression style are independent
dimensions. Presentation (MALE/FEMALE/NEUTRAL/CUSTOM) is a starting
preset and is NEVER hard-locked to voice selection.
"""
from __future__ import annotations

import copy
import random
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from avatar.protocol import CUSTOM, FEMALE, MALE, NEUTRAL, PRESENTATION_PROFILES

# Creation modes (architecture; providers determine achievable fidelity).
PRESET = "PRESET"
CUSTOMIZE_FROM_PRESET = "CUSTOMIZE_FROM_PRESET"
RANDOM_GENERATE = "RANDOM_GENERATE"
IMAGE_REFERENCE = "IMAGE_REFERENCE"
GUIDED_CAMERA_CAPTURE = "GUIDED_CAMERA_CAPTURE"
IMPORT_GLTF = "IMPORT_GLTF"
IMPORT_GLB = "IMPORT_GLB"
IMPORT_VRM = "IMPORT_VRM"

CREATION_MODES = (
    PRESET, CUSTOMIZE_FROM_PRESET, RANDOM_GENERATE, IMAGE_REFERENCE,
    GUIDED_CAMERA_CAPTURE, IMPORT_GLTF, IMPORT_GLB, IMPORT_VRM,
)

# Support levels.
PROFILE_SUPPORTED = "PROFILE_SUPPORTED"
RENDERED_SUPPORTED = "RENDERED_SUPPORTED"
PROVIDER_REQUIRED = "PROVIDER_REQUIRED"

# Fields the procedural reference GLB actually renders (nodes/expressions).
_RENDERED_FIELDS = frozenset({
    "presentation", "expressions", "gestures", "jaw", "eyes",
})

# Fields that need a morph/reconstruction provider for true geometry change.
_PROVIDER_FIELDS = frozenset({
    "head_shape", "face_proportions", "jaw_geometry", "cheekbones", "chin",
    "nose_geometry", "body_proportions", "height_geometry",
})

SIMPLE_FIELDS = (
    "presentation", "skin_tone", "hair_style", "hair_colour",
    "clothing", "avatar_asset",
)


@dataclass
class AppearanceProfile:
    """Configurable appearance. Values are stored; rendering support varies
    per field (see support_for). Appearance carries NO intelligence."""
    presentation: str = NEUTRAL
    height_cm: float = 170.0
    body_proportions: str = "average"
    body_build: str = "average"
    head_shape: str = "oval"
    face_proportions: str = "balanced"
    jaw: str = "medium"
    jaw_geometry: str = "medium"
    cheekbones: str = "medium"
    chin: str = "rounded"
    nose: str = "medium"
    nose_geometry: str = "medium"
    eyes: str = "brown-round"
    eyebrows: str = "medium"
    ears: str = "medium"
    mouth_lips: str = "medium"
    skin_tone: str = "medium"
    hair_style: str = "short"
    hair_colour: str = "brown"
    facial_hair: str = "none"
    body_hair: str = "none"
    age_appearance: str = "adult"
    scars: str = "none"
    freckles: str = "none"
    tattoos: str = "none"
    piercings: str = "none"
    accessories: str = "none"
    clothing: str = "casual"
    footwear: str = "shoes"
    skins_outfits: str = "default"
    expressions: str = "neutral"
    gestures: str = "subtle"
    avatar_asset: str = "reference-avatar.glb"
    source_mode: str = PRESET
    source_ref: str = ""

    def validate(self) -> tuple[bool, str]:
        if self.presentation not in PRESENTATION_PROFILES:
            return False, f"unknown presentation: {self.presentation!r}"
        if not 50.0 <= float(self.height_cm) <= 250.0:
            return False, "height_cm out of range"
        return True, ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def simple_view(self) -> dict[str, Any]:
        d = self.to_dict()
        return {k: d[k] for k in SIMPLE_FIELDS}

    def advanced_view(self) -> dict[str, Any]:
        return self.to_dict()


def support_for(field_name: str) -> str:
    """How is this appearance field realized here?"""
    if field_name in _RENDERED_FIELDS:
        return RENDERED_SUPPORTED
    if field_name in _PROVIDER_FIELDS:
        return PROVIDER_REQUIRED
    return PROFILE_SUPPORTED


@dataclass
class VoiceSelection:
    """Voice configuration: associated with, but independent from,
    appearance. Any combination may be overridden by the user."""
    voice_id: str = ""
    language: str = "en"
    locale: str = "en-US"
    accent: str = ""
    speaking_style: str = "neutral"
    rate: float = 1.0
    pitch: float = 1.0
    expressiveness: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def suggest_voices(presentation: str) -> list[str]:
    """Compatible voice suggestions only. Never a lock: the caller may
    assign any voice_id to any presentation."""
    if presentation == MALE:
        return ["masc-voice-a", "masc-voice-b", "neutral-voice-a"]
    if presentation == FEMALE:
        return ["fem-voice-a", "fem-voice-b", "neutral-voice-a"]
    return ["neutral-voice-a", "neutral-voice-b"]


@dataclass
class PersonaProfile:
    """Personality/expression style. Independent from appearance/voice."""
    personality: str = "helpful"
    expression_style: str = "subtle"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_PRESETS: dict[str, dict[str, Any]] = {
    "neutral-default": {"presentation": NEUTRAL, "skin_tone": "medium",
                        "hair_style": "short", "clothing": "casual"},
    "masc-default": {"presentation": MALE, "skin_tone": "medium",
                     "hair_style": "short", "facial_hair": "none",
                     "clothing": "casual"},
    "fem-default": {"presentation": FEMALE, "skin_tone": "medium",
                    "hair_style": "long", "clothing": "casual"},
    "custom-blank": {"presentation": CUSTOM},
}


def list_presets() -> list[str]:
    return sorted(_PRESETS)


class AvatarCreator:
    """Non-destructive layered customization with undo/redo + history."""

    def __init__(self):
        self._undo: list[AppearanceProfile] = []
        self._redo: list[AppearanceProfile] = []
        self._history: list[dict[str, Any]] = []

    def _snapshot(self, profile: AppearanceProfile, action: str) -> None:
        self._history.append({"action": action,
                              "profile": profile.to_dict()})

    def create(self, mode: str, preset: str = "neutral-default",
               seed: int | None = None, **overrides) -> AppearanceProfile:
        if mode not in CREATION_MODES:
            raise ValueError(f"unknown creation mode: {mode!r}")
        if mode == PRESET:
            base = dict(_PRESETS.get(preset, _PRESETS["neutral-default"]))
            prof = AppearanceProfile(source_mode=mode, source_ref=preset,
                                     **{**base, **overrides})
        elif mode == CUSTOMIZE_FROM_PRESET:
            base = dict(_PRESETS.get(preset, _PRESETS["neutral-default"]))
            prof = AppearanceProfile(source_mode=mode, source_ref=preset,
                                     **{**base, **overrides})
        elif mode == RANDOM_GENERATE:
            rng = random.Random(seed)
            prof = AppearanceProfile(
                source_mode=mode, source_ref=f"seed:{seed}",
                presentation=rng.choice(list(PRESENTATION_PROFILES)),
                skin_tone=rng.choice(["light", "medium", "dark", "deep"]),
                hair_style=rng.choice(["short", "long", "curly", "bald", "ponytail"]),
                hair_colour=rng.choice(["black", "brown", "blonde", "red", "grey"]),
                clothing=rng.choice(["casual", "formal", "sport", "robe"]),
                **overrides)
        elif mode in (IMPORT_GLTF, IMPORT_GLB, IMPORT_VRM):
            ref = str(overrides.get("asset_path", ""))
            want = {IMPORT_GLTF: ".gltf", IMPORT_GLB: ".glb", IMPORT_VRM: ".vrm"}[mode]
            if not ref.lower().endswith(want):
                raise ValueError(f"{mode} requires a {want} asset path")
            prof = AppearanceProfile(source_mode=mode, source_ref=ref,
                                     avatar_asset=ref, **{k: v for k, v in overrides.items()
                                                          if k != "asset_path"})
        elif mode in (IMAGE_REFERENCE, GUIDED_CAMERA_CAPTURE):
            ref = str(overrides.get("reference", ""))
            if not ref:
                raise ValueError(f"{mode} requires a reference id")
            # Geometry from photos needs a reconstruction provider; the
            # reference + profile are stored, geometry stays provider-gated.
            prof = AppearanceProfile(source_mode=mode, source_ref=ref,
                                     **{k: v for k, v in overrides.items()
                                        if k != "reference"})
        else:  # pragma: no cover - all modes enumerated above
            raise ValueError(mode)
        ok, err = prof.validate()
        if not ok:
            raise ValueError(err)
        self._snapshot(prof, f"create:{mode}")
        return prof

    def apply_change(self, profile: AppearanceProfile,
                     **changes) -> AppearanceProfile:
        """Layered reversible change: push current, apply, clear redo."""
        self._undo.append(copy.deepcopy(profile))
        self._redo.clear()
        for k, v in changes.items():
            if not hasattr(profile, k):
                raise ValueError(f"unknown appearance field: {k!r}")
            setattr(profile, k, v)
        ok, err = profile.validate()
        if not ok:
            raise ValueError(err)
        self._snapshot(profile, f"change:{sorted(changes)}")
        return profile

    def undo(self, profile: AppearanceProfile) -> AppearanceProfile:
        if not self._undo:
            raise ValueError("nothing to undo")
        self._redo.append(copy.deepcopy(profile))
        prev = self._undo.pop()
        self._snapshot(prev, "undo")
        return prev

    def redo(self, profile: AppearanceProfile) -> AppearanceProfile:
        if not self._redo:
            raise ValueError("nothing to redo")
        self._undo.append(copy.deepcopy(profile))
        nxt = self._redo.pop()
        self._snapshot(nxt, "redo")
        return nxt

    def reset_section(self, profile: AppearanceProfile,
                      section: str) -> AppearanceProfile:
        groups = {
            "face": ("head_shape", "face_proportions", "jaw", "cheekbones",
                     "chin", "nose", "eyes", "eyebrows", "ears", "mouth_lips"),
            "hair": ("hair_style", "hair_colour", "facial_hair", "body_hair"),
            "body": ("height_cm", "body_proportions", "body_build"),
            "style": ("clothing", "footwear", "accessories", "skins_outfits",
                      "tattoos", "piercings", "scars", "freckles"),
        }
        if section not in groups:
            raise ValueError(f"unknown section: {section!r}")
        blank = AppearanceProfile()
        return self.apply_change(profile, **{f: getattr(blank, f)
                                             for f in groups[section]})

    def reset_all(self, profile: AppearanceProfile) -> AppearanceProfile:
        blank = AppearanceProfile()
        return self.apply_change(profile, **blank.to_dict())

    def history(self) -> list[dict[str, Any]]:
        return list(self._history)


class PresetStore:
    """Save/duplicate/version avatar presets with provenance."""

    def __init__(self):
        self._presets: dict[str, dict[str, Any]] = {}
        self._versions: dict[str, list[dict[str, Any]]] = {}

    def save(self, name: str, profile: AppearanceProfile,
             provenance: str = "user") -> dict[str, Any]:
        if not name or len(name) > 64:
            raise ValueError("bad preset name")
        entry = {"name": name, "profile": profile.to_dict(),
                 "provenance": provenance, "version": 1}
        if name in self._presets:
            entry["version"] = self._presets[name]["version"] + 1
        self._presets[name] = entry
        self._versions.setdefault(name, []).append(copy.deepcopy(entry))
        return copy.deepcopy(entry)

    def duplicate(self, name: str, new_name: str) -> dict[str, Any]:
        if name not in self._presets:
            raise KeyError(f"unknown preset: {name!r}")
        if not new_name or new_name in self._presets:
            raise ValueError("bad or duplicate new preset name")
        dup = copy.deepcopy(self._presets[name])
        dup["name"] = new_name
        dup["version"] = 1
        self._presets[new_name] = dup
        self._versions.setdefault(new_name, []).append(copy.deepcopy(dup))
        return copy.deepcopy(dup)

    def get(self, name: str) -> dict[str, Any]:
        return copy.deepcopy(self._presets[name])

    def list(self) -> list[str]:
        return sorted(self._presets)

    def versions(self, name: str) -> list[dict[str, Any]]:
        return copy.deepcopy(self._versions.get(name, []))
