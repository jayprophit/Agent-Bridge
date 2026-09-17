"""Genesis Avatar Interface - UI Modes for Genesis Integration.

This module implements the avatar interface mapping for Genesis 2.4,
providing four UI modes:
- HIDDEN: No visible avatar presence
- SMALL: Compact avatar indicator (status bar/icon)
- STANDARD: Standard avatar panel (sidebar/docked)
- FULL SCREEN: Immersive full-screen avatar workspace

The avatar is the user-facing interface for Genesis cognition.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable
from abc import ABC, abstractmethod
import json
from pathlib import Path


class AvatarUIMode(Enum):
    """Avatar UI visibility modes."""
    HIDDEN = "hidden"
    SMALL = "small"
    STANDARD = "standard"
    FULL_SCREEN = "full_screen"


class AvatarState(Enum):
    """Avatar operational states."""
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    AWAITING_INPUT = "awaiting_input"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class AvatarCapabilities:
    """Capabilities exposed by the avatar interface."""
    can_propose_plans: bool = True
    can_execute_actions: bool = True
    can_show_memory: bool = True
    can_show_session: bool = True
    can_accept_voice: bool = False
    can_show_code: bool = True
    can_show_visuals: bool = True
    can_interact_files: bool = True
    can_manage_tasks: bool = True
    custom: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AvatarConfig:
    """Configuration for avatar interface."""
    mode: AvatarUIMode = AvatarUIMode.STANDARD
    position: str = "right"  # left, right, bottom, top, center
    width: int = 400
    height: int = 600
    opacity: float = 1.0
    theme: str = "system"  # light, dark, system
    auto_hide: bool = False
    show_state_indicator: bool = True
    show_capability_badges: bool = True
    capabilities: AvatarCapabilities = field(default_factory=AvatarCapabilities)
    hotkey_toggle: Optional[str] = "ctrl+shift+g"
    hotkey_cycle_mode: Optional[str] = "ctrl+shift+alt+g"


class AvatarInterface(ABC):
    """Abstract base for avatar UI implementations."""
    
    @abstractmethod
    def set_mode(self, mode: AvatarUIMode) -> None:
        """Change the UI mode."""
        pass
    
    @abstractmethod
    def set_state(self, state: AvatarState) -> None:
        """Update the avatar's operational state."""
        pass
    
    @abstractmethod
    def show_message(self, message: str, level: str = "info") -> None:
        """Display a message in the avatar UI."""
        pass
    
    @abstractmethod
    def show_plan(self, plan: Dict[str, Any]) -> None:
        """Display a proposed plan."""
        pass
    
    @abstractmethod
    def show_memory(self, memory_data: Dict[str, Any]) -> None:
        """Display memory/session information."""
        pass
    
    @abstractmethod
    def request_input(self, prompt: str, input_type: str = "text") -> Any:
        """Request user input."""
        pass
    
    @abstractmethod
    def update_capabilities(self, capabilities: AvatarCapabilities) -> None:
        """Update displayed capabilities."""
        pass
    
    @abstractmethod
    def get_config(self) -> AvatarConfig:
        """Get current configuration."""
        pass
    
    @abstractmethod
    def set_config(self, config: AvatarConfig) -> None:
        """Update configuration."""
        pass


class AvatarBinding:
    """Binds Genesis cognition to avatar interface.

    Genesis 2.4 model: the visible avatar is the Spiritual Body interface of
    a Genesis identity (processor/brain). Binding by genesis_id (headless mock
    interface unless one is supplied) plus project() covers identity-bound
    projection; binding an explicit interface covers UI-driven use.
    """

    # Identity-state string -> avatar operational state (2.4 mapping).
    IDENTITY_STATE_MAP = {
        "working": "EXECUTING", "executing": "EXECUTING",
        "thinking": "THINKING", "idle": "IDLE",
        "awaiting_input": "AWAITING_INPUT", "awaiting": "AWAITING_INPUT",
        "error": "ERROR", "disabled": "DISABLED",
    }

    def __init__(self, interface: Optional[AvatarInterface] = None,
                 config: Optional[AvatarConfig] = None,
                 genesis_id: str = ""):
        self.genesis_id = genesis_id or ""
        self.interface = interface or MockAvatarInterface()
        self.config = config or AvatarConfig()
        self.current_state = AvatarState.IDLE
        self.current_mode = self.config.mode
        self._mode_change_callbacks: list[Callable[[AvatarUIMode], None]] = []
        self._state_change_callbacks: list[Callable[[AvatarState], None]] = []
        
        # Apply initial config
        self.interface.set_config(self.config)
        self.interface.set_mode(self.current_mode)
    
    def on_mode_change(self, callback: Callable[[AvatarUIMode], None]) -> None:
        """Register callback for mode changes."""
        self._mode_change_callbacks.append(callback)
    
    def on_state_change(self, callback: Callable[[AvatarState], None]) -> None:
        """Register callback for state changes."""
        self._state_change_callbacks.append(callback)
    
    def set_mode(self, mode: AvatarUIMode) -> None:
        """Change the avatar UI mode."""
        if mode != self.current_mode:
            old_mode = self.current_mode
            self.current_mode = mode
            self.config.mode = mode
            self.interface.set_mode(mode)
            for callback in self._mode_change_callbacks:
                try:
                    callback(mode)
                except Exception:
                    pass
    
    def cycle_mode(self) -> None:
        """Cycle to the next UI mode."""
        modes = list(AvatarUIMode)
        current_index = modes.index(self.current_mode)
        next_mode = modes[(current_index + 1) % len(modes)]
        self.set_mode(next_mode)
    
    def set_state(self, state: AvatarState) -> None:
        """Update the avatar's operational state."""
        if state != self.current_state:
            self.current_state = state
            self.interface.set_state(state)
            for callback in self._state_change_callbacks:
                try:
                    callback(state)
                except Exception:
                    pass
    
    def propose_plan(self, plan: Dict[str, Any]) -> None:
        """Display a proposed plan from Genesis cognition."""
        self.set_state(AvatarState.AWAITING_INPUT)
        self.interface.show_plan(plan)
    
    def execute_action(self, action: Dict[str, Any]) -> None:
        """Show action execution."""
        self.set_state(AvatarState.EXECUTING)
        self.interface.show_message(f"Executing: {action.get('description', 'Action')}")
    
    def complete_action(self, result: Any) -> None:
        """Show action completion."""
        self.set_state(AvatarState.IDLE)
        if isinstance(result, dict) and result.get("success"):
            self.interface.show_message("Action completed successfully", "success")
        else:
            self.interface.show_message(f"Action completed: {result}", "info")
    
    def show_error(self, error: str) -> None:
        """Show error state."""
        self.set_state(AvatarState.ERROR)
        self.interface.show_message(f"Error: {error}", "error")
    
    def think(self, thought: str) -> None:
        """Show thinking state."""
        self.set_state(AvatarState.THINKING)
        self.interface.show_message(thought, "thinking")
    
    def update_memory_display(self, memory_data: Dict[str, Any]) -> None:
        """Update memory/session display."""
        self.interface.show_memory(memory_data)
    
    def request_user_input(self, prompt: str, input_type: str = "text") -> Any:
        """Request input from user."""
        self.set_state(AvatarState.AWAITING_INPUT)
        return self.interface.request_input(prompt, input_type)

    def project(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Project a Genesis identity cognition state onto the avatar.

        Maps the identity state string onto the avatar operational state,
        surfaces the summary, and echoes the projection record including the
        bound genesis_id (empty unless identity-bound).
        """
        raw = str((state or {}).get("state", "idle"))
        try:
            mapped = AvatarState[self.IDENTITY_STATE_MAP.get(raw.lower(), "IDLE")]
        except KeyError:
            mapped = AvatarState.IDLE
        self.set_state(mapped)
        summary = (state or {}).get("summary", "")
        if summary:
            self.interface.show_message(str(summary), "info")
        return {"state": raw, "summary": summary,
                "genesis_id": self.genesis_id,
                "avatar_state": self.current_state.value,
                "mode": self.current_mode.value}
    
    def get_config(self) -> AvatarConfig:
        """Get current configuration."""
        return self.config
    
    def update_config(self, **kwargs) -> None:
        """Update configuration."""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        self.interface.set_config(self.config)


class MockAvatarInterface(AvatarInterface):
    """Mock implementation for testing and headless environments."""

    @staticmethod
    def _emit(text: str) -> None:
        # Windows consoles (cp1252) cannot encode glyph prefixes; fall
        # back to ascii-safe output rather than crashing the caller.
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode("ascii", "replace").decode("ascii"))

    def __init__(self):
        self._config = AvatarConfig()
        self._mode = AvatarUIMode.HIDDEN
        self._state = AvatarState.IDLE
        self._messages = []
        self._plans = []
        self._memory = {}
        self._capabilities = AvatarCapabilities()
    
    def set_mode(self, mode: AvatarUIMode) -> None:
        self._mode = mode
        self._emit(f"[Avatar] Mode changed to: {mode.value}")
    
    def set_state(self, state: AvatarState) -> None:
        self._state = state
        self._emit(f"[Avatar] State changed to: {state.value}")
    
    def show_message(self, message: str, level: str = "info") -> None:
        self._messages.append({"message": message, "level": level})
        prefix = {"info": "ℹ", "success": "✓", "error": "✗", "thinking": "⟳"}.get(level, "•")
        self._emit(f"[Avatar] {prefix} {message}")
    
    def show_plan(self, plan: Dict[str, Any]) -> None:
        self._plans.append(plan)
        self._emit(f"[Avatar] Plan proposed: {json.dumps(plan, indent=2)[:200]}...")
    
    def show_memory(self, memory_data: Dict[str, Any]) -> None:
        self._memory = memory_data
        self._emit(f"[Avatar] Memory updated: {len(memory_data)} items")
    
    def request_input(self, prompt: str, input_type: str = "text") -> Any:
        self._emit(f"[Avatar] Input requested ({input_type}): {prompt}")
        return None
    
    def update_capabilities(self, capabilities: AvatarCapabilities) -> None:
        self._capabilities = capabilities
        self._emit(f"[Avatar] Capabilities updated")
    
    def get_config(self) -> AvatarConfig:
        return self._config
    
    def set_config(self, config: AvatarConfig) -> None:
        self._config = config
        self._emit(f"[Avatar] Config updated: mode={config.mode.value}")


def create_avatar_binding(mode: AvatarUIMode = AvatarUIMode.STANDARD) -> AvatarBinding:
    """Factory function to create avatar binding with mock interface."""
    config = AvatarConfig(mode=mode)
    interface = MockAvatarInterface()
    return AvatarBinding(interface, config)


# One live binding per genesis_id per process: every presentation surface
# projecting the same Genesis identity shares one binding, so mode/state
# stay consistent and no duplicate identity projections exist.
_BINDINGS: dict[str, AvatarBinding] = {}


def binding_for(genesis_id: str) -> AvatarBinding:
    """Return the shared live binding for a genesis_id (created on demand)."""
    key = genesis_id or ""
    bound = _BINDINGS.get(key)
    if bound is None:
        bound = AvatarBinding(genesis_id=key)
        _BINDINGS[key] = bound
    return bound


def project_genesis_runtime(binding: AvatarBinding,
                            runtime: Any) -> Dict[str, Any]:
    """Project a LIVE Genesis runtime identity onto a bound avatar.

    Reads only real runtime fields (identity.genesis_id/display_name/
    active_model, sessions). Never invents an identity: empty genesis_id
    yields projected=False and leaves the binding untouched. A binding
    already bound to a different id is never overwritten (no identity
    hijack); that case also yields projected=False.
    """
    identity = getattr(runtime, "identity", None)
    genesis_id = str(getattr(identity, "genesis_id", "") or "")
    if not genesis_id:
        return {"genesis_id": "", "projected": False,
                "reason": "no_live_identity",
                "avatar_state": binding.current_state.value,
                "mode": binding.current_mode.value}
    if binding.genesis_id and binding.genesis_id != genesis_id:
        return {"genesis_id": binding.genesis_id, "projected": False,
                "reason": "identity_mismatch",
                "avatar_state": binding.current_state.value,
                "mode": binding.current_mode.value}
    if not binding.genesis_id:
        binding.genesis_id = genesis_id
    sessions = getattr(runtime, "sessions", None) or {}
    try:
        open_count = sum(
            1 for s in sessions.values()
            if str(getattr(s, "state", "OPEN")) not in ("CLOSED", "DONE"))
    except Exception:
        open_count = 0
    active_model = str(getattr(identity, "active_model", "") or "")
    display = str(getattr(identity, "display_name", "") or "Genesis")
    state = "working" if open_count else "idle"
    summary = ("%s (%s) - %d open session(s) - model %s"
               % (display, genesis_id, open_count, active_model or "none"))
    record = binding.project({"state": state, "summary": summary})
    record["projected"] = True
    return record


# Export for Genesis integration
__all__ = [
    "AvatarUIMode",
    "AvatarState",
    "AvatarCapabilities",
    "AvatarConfig",
    "AvatarInterface",
    "AvatarBinding",
    "MockAvatarInterface",
    "create_avatar_binding",
    "binding_for",
    "project_genesis_runtime",
]