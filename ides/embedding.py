"""IDE embedding contract (v0.8, Part I). Bridge stays a bridge.

Host IDEs embed the Bridge panel (WebView) and supply host context:
workspace, selection, diagnostics, terminal/build/test events, diff/approval
UI. Host modes: STANDALONE, EMBEDDED_IDE_LEFT, EMBEDDED_IDE_RIGHT, HEADLESS.
The same session survives mode changes. Core Bridge never depends on VS Code
or any single IDE; the reference adapter below is interface-only shape.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

STANDALONE = "STANDALONE"
EMBEDDED_IDE_LEFT = "EMBEDDED_IDE_LEFT"
EMBEDDED_IDE_RIGHT = "EMBEDDED_IDE_RIGHT"
HEADLESS = "HEADLESS"

HOST_MODES = (STANDALONE, EMBEDDED_IDE_LEFT, EMBEDDED_IDE_RIGHT, HEADLESS)


@dataclass
class HostSelection:
    file: str = ""
    start_line: int = 0
    start_col: int = 0
    end_line: int = 0
    end_col: int = 0
    selected_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HostContext:
    """What the host IDE provides to the Bridge panel."""
    ide_id: str = ""
    workspace_root: str = ""
    open_files: list[str] = field(default_factory=list)
    selection: HostSelection = field(default_factory=HostSelection)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    host_mode: str = STANDALONE
    session_id: str = ""  # SAME session as Chat/Work/voice/call

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["selection"] = self.selection.to_dict()
        return data

    def validate(self) -> tuple[bool, str]:
        if self.host_mode not in HOST_MODES:
            return False, f"unknown host mode: {self.host_mode!r}"
        return True, ""


@dataclass
class DiffApproval:
    """Diff/approval UI payload shared with the host."""
    diff_id: str
    session_id: str = ""
    files: list[str] = field(default_factory=list)
    approved: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReferenceIDEAdapter:
    """Reference host-integration shape (interface-only; no vscode dependency).

    A real VS Code WebView/extension (or any future IDE) implements these
    hooks against its own APIs. The Bridge core never imports it.
    """

    ide_id: str = "reference-ide"
    supported_modes: tuple = (EMBEDDED_IDE_LEFT, EMBEDDED_IDE_RIGHT, HEADLESS)

    def host_context(self) -> HostContext:
        raise NotImplementedError("host IDE provides workspace context")

    def show_diff(self, approval: DiffApproval) -> dict:
        raise NotImplementedError("host IDE renders diff/approval UI")

    def terminal_event(self, event: dict) -> dict:
        raise NotImplementedError("host IDE forwards terminal/build/test events")
