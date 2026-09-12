"""Email + telephony communications (v0.8, provider-neutral)."""
from __future__ import annotations

from comms.telephone import (
    ACTIVE, ANSWERED, AUTO_ANSWER_ALL, AUTO_ANSWER_TRUSTED, BUSINESS_HOURS,
    DO_NOT_DISTURB, ESCALATED, HANGUP, MANUAL_ANSWER, REJECTED, RINGING,
    CallProvider, CallSession, LoopbackCallProvider, TelephoneAgent,
)

__all__ = [
    "ACTIVE", "ANSWERED", "AUTO_ANSWER_ALL", "AUTO_ANSWER_TRUSTED",
    "BUSINESS_HOURS", "DO_NOT_DISTURB", "ESCALATED", "HANGUP",
    "MANUAL_ANSWER", "REJECTED", "RINGING",
    "CallProvider", "CallSession", "LoopbackCallProvider", "TelephoneAgent",
]
