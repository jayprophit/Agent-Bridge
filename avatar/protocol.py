"""Avatar Event Protocol (v0.8, Part G). Backend-agnostic presentation events.

The avatar is NOT the intelligence: DefaultAgent emits these events and any
renderer (Three.js, 2D fallback, future clients) presents them. Presentation
profile (MALE/FEMALE/NEUTRAL/CUSTOM) is explicit configuration; never infer
gender from voice pitch.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Stable avatar events.
IDLE = "IDLE"
LISTENING = "LISTENING"
THINKING = "THINKING"
SPEAKING = "SPEAKING"
TOOL_RUNNING = "TOOL_RUNNING"
SUCCESS = "SUCCESS"
WARNING = "WARNING"
ERROR = "ERROR"
EMOTION = "EMOTION"
GESTURE = "GESTURE"
VISEME = "VISEME"
GAZE = "GAZE"
HEAD_MOVEMENT = "HEAD_MOVEMENT"
BODY_ANIMATION = "BODY_ANIMATION"

AVATAR_EVENTS = (
    IDLE, LISTENING, THINKING, SPEAKING, TOOL_RUNNING, SUCCESS, WARNING,
    ERROR, EMOTION, GESTURE, VISEME, GAZE, HEAD_MOVEMENT, BODY_ANIMATION,
)

# Presentation profiles.
MALE = "MALE"
FEMALE = "FEMALE"
NEUTRAL = "NEUTRAL"
CUSTOM = "CUSTOM"

PRESENTATION_PROFILES = (MALE, FEMALE, NEUTRAL, CUSTOM)

# Controlled expressions (no theatrical animation).
EXPRESSIONS = ("neutral", "happy", "concerned", "thinking", "surprised",
               "confident")

# Viseme set (provider timestamps preferred; amplitude fallback otherwise).
VISEMES = ("sil", "PP", "FF", "TH", "DD", "kk", "CH", "SS", "nn", "RR",
           "aa", "E", "I", "O", "U")

# Viseme -> jaw openness 0.0-1.0 (amplitude fallback + blendshape mapping).
VISEME_JAW = {"sil": 0.0, "PP": 0.05, "FF": 0.15, "TH": 0.2, "DD": 0.35,
              "kk": 0.3, "CH": 0.35, "SS": 0.25, "nn": 0.3, "RR": 0.4,
              "aa": 1.0, "E": 0.55, "I": 0.35, "O": 0.7, "U": 0.4}


@dataclass
class AvatarEvent:
    """One presentation event from the agent to the renderer."""
    event: str
    session_id: str = ""
    text: str = ""
    emotion: str = "neutral"
    gesture: str = ""
    viseme: str = ""
    intensity: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> tuple[bool, str]:
        if self.event not in AVATAR_EVENTS:
            return False, f"unknown avatar event: {self.event!r}"
        if self.event == EMOTION and self.emotion not in EXPRESSIONS:
            return False, f"unknown expression: {self.emotion!r}"
        if self.event == VISEME and self.viseme not in VISEMES:
            return False, f"unknown viseme: {self.viseme!r}"
        if not 0.0 <= self.intensity <= 1.0:
            return False, "intensity must be 0.0-1.0"
        return True, ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AvatarProfile:
    """Explicit persona/presentation configuration (owner-overridable)."""
    presentation: str = NEUTRAL
    voice_id: str = ""
    avatar_asset: str = "reference-avatar.glb"
    expressions_enabled: bool = True
    gestures_enabled: bool = True
    lip_sync: str = "viseme"  # viseme | phoneme | amplitude

    def validate(self) -> tuple[bool, str]:
        if self.presentation not in PRESENTATION_PROFILES:
            return False, f"unknown presentation: {self.presentation!r}"
        if self.lip_sync not in ("viseme", "phoneme", "amplitude"):
            return False, f"unknown lip_sync: {self.lip_sync!r}"
        return True, ""


def amplitude_to_jaw(amplitude: float) -> float:
    """Audio-amplitude fallback: 0.0-1.0 amplitude -> jaw openness."""
    return max(0.0, min(1.0, float(amplitude)))
