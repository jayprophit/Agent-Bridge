"""Real-time voice agent (v0.8, provider-neutral)."""
from __future__ import annotations

from voice.pipeline import (
    AUTO_ANSWER_ALL, AUTO_ANSWER_TRUSTED, BUSINESS_HOURS, CONVERSATION,
    DO_NOT_DISTURB, MANUAL_ANSWER, PUSH_TO_TALK, VoicePipeline,
    VoiceSession, VoiceTurn,
)

__all__ = [
    "AUTO_ANSWER_ALL", "AUTO_ANSWER_TRUSTED", "BUSINESS_HOURS", "CONVERSATION",
    "DO_NOT_DISTURB", "MANUAL_ANSWER", "PUSH_TO_TALK", "VoicePipeline",
    "VoiceSession", "VoiceTurn",
]
