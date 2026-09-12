"""Lightweight per-session model competence observations (v0.4, local only).

Measurements feed routing/escalation hints. Never permanently labels a
model from one session.
"""
from __future__ import annotations

from typing import Any


class CompetenceTracker:
    def __init__(self):
        self.requested = 0
        self.valid = 0
        self.malformed = 0
        self.executed_ok = 0
        self.executed_fail = 0
        self.syntax_error_runs = 0
        self.corrections = 0  # fail -> different action -> success
        self.loops = 0
        self.reviewer_agreements = 0
        self.reviewer_disagreements = 0
        self._last_failed = False

    def note_request(self, valid: bool) -> None:
        self.requested += 1
        if valid:
            self.valid += 1
        else:
            self.malformed += 1

    def note_execution(self, ok: bool, stderr: str = "") -> None:
        if ok:
            self.executed_ok += 1
            if self._last_failed:
                self.corrections += 1
            self._last_failed = False
        else:
            self.executed_fail += 1
            self._last_failed = True
            if "SyntaxError" in (stderr or ""):
                self.syntax_error_runs += 1

    def note_loop(self) -> None:
        self.loops += 1

    def note_review(self, agreed_with_truth: bool) -> None:
        if agreed_with_truth:
            self.reviewer_agreements += 1
        else:
            self.reviewer_disagreements += 1

    def summary(self) -> dict[str, Any]:
        total = max(1, self.requested)
        return {
            "valid_action_ratio": round(self.valid / total, 3),
            "malformed": self.malformed,
            "executed_ok": self.executed_ok,
            "executed_fail": self.executed_fail,
            "corrections": self.corrections,
            "syntax_error_runs": self.syntax_error_runs,
            "loops": self.loops,
            "reviewer_agreement": [self.reviewer_agreements,
                                   self.reviewer_disagreements],
            "hint": self._hint(),
        }

    def _hint(self) -> str:
        if self.requested >= 6 and self.valid / self.requested < 0.5:
            return "malformed-output threshold: consider fallback model"
        if self.syntax_error_runs >= 3:
            return "repeated syntax errors: simplify task wording"
        if self.loops >= 2:
            return "repeated loops: escalate or change strategy"
        return "nominal"
