"""3D avatar presentation layer (v0.8, Part G). Events, not intelligence."""
from __future__ import annotations

from avatar.protocol import (
    AVATAR_EVENTS, BODY_ANIMATION, EMOTION, ERROR, EXPRESSIONS, FEMALE,
    GAZE, GESTURE, HEAD_MOVEMENT, IDLE, LISTENING, MALE, NEUTRAL,
    PRESENTATION_PROFILES, SPEAKING, SUCCESS, THINKING, TOOL_RUNNING,
    VISEME, VISEMES, VISEME_JAW, WARNING, CUSTOM,
    AvatarEvent, AvatarProfile, amplitude_to_jaw,
)
from avatar import creator as creator
from avatar import capture as capture

__all__ = [
    "AVATAR_EVENTS", "BODY_ANIMATION", "EMOTION", "ERROR", "EXPRESSIONS",
    "FEMALE", "GAZE", "GESTURE", "HEAD_MOVEMENT", "IDLE", "LISTENING",
    "MALE", "NEUTRAL", "PRESENTATION_PROFILES", "SPEAKING", "SUCCESS",
    "THINKING", "TOOL_RUNNING", "VISEME", "VISEMES", "VISEME_JAW",
    "WARNING", "CUSTOM",
    "AvatarEvent", "AvatarProfile", "amplitude_to_jaw",
    "creator", "capture",
]
