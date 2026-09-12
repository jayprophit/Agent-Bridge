"""GitHub Copilot provider adapter (v0.7). Interface placeholder.

IMPORTANT: GitHub Copilot does NOT currently have an official public API
for programmatic access. This adapter is an INTERFACE_ONLY placeholder.

When GitHub releases an official API for Copilot, this adapter should be
implemented using that official integration.

Current status: INTERFACE_ONLY - no official public API available.
"""
from __future__ import annotations

from typing import Any

from models.provider_adapter import ProviderAdapter
from models.provider_registry import (
    NOT_CONFIGURED, ProviderRecord
)


class CopilotProvider(ProviderAdapter):
    """Interface placeholder for GitHub Copilot.
    
    IMPORTANT: This is currently INTERFACE_ONLY as GitHub Copilot does not
    have an official public API. This adapter serves as a placeholder for when
    GitHub releases official programmatic access.
    """
    
    provider_id = "copilot"
    provider_family = "github_copilot"
    
    def __init__(self):
        self.api_configured = False
    
    def discover(self) -> dict[str, Any]:
        """No official Copilot API available for discovery."""
        return {
            "provider_id": self.provider_id,
            "provider_family": self.provider_family,
            "models": [],
            "error": "INTERFACE_ONLY: No official GitHub Copilot public API available"
        }
    
    def authenticate(self, credentials: dict[str, Any] | None = None) -> dict[str, Any]:
        """No official Copilot authentication API available."""
        return {
            "provider_id": self.provider_id,
            "authenticated": False,
            "error": "INTERFACE_ONLY: No official GitHub Copilot authentication API available"
        }
    
    def list_models(self) -> list[dict[str, Any]]:
        """No official Copilot model listing available."""
        return []
    
    def model_info(self, model_id: str) -> dict[str, Any]:
        """No official Copilot model info available."""
        return {
            "model_id": model_id,
            "available": False,
            "error": "INTERFACE_ONLY: No official GitHub Copilot API available"
        }
    
    def capabilities(self) -> dict[str, Any]:
        """Report Copilot capabilities (interface only)."""
        return {
            "provider_id": self.provider_id,
            "provider_family": self.provider_family,
            "supports_streaming": False,
            "supports_tool_calling": False,
            "supports_vision": False,
            "supports_audio_input": False,
            "supports_audio_output": False,
            "supports_structured_output": False,
            "local_or_remote": "unknown",
            "requires_network": True,
            "requires_auth": True,
            "status": "INTERFACE_ONLY"
        }
    
    def context_limit(self, model_id: str) -> int:
        """No context limit information available."""
        return 0
    
    def generate(self, model_id: str, messages: list[dict[str, Any]],
                **kwargs) -> dict[str, Any]:
        """No official Copilot generation API available."""
        return {
            "ok": False,
            "error": "INTERFACE_ONLY: No official GitHub Copilot generation API available"
        }
    
    def stream(self, model_id: str, messages: list[dict[str, Any]],
               **kwargs):
        """No official Copilot streaming API available."""
        yield "INTERFACE_ONLY: No official GitHub Copilot API available"
    
    def tool_call(self, model_id: str, messages: list[dict[str, Any]],
                  tools: list[dict[str, Any]], **kwargs) -> dict[str, Any]:
        """No official Copilot tool calling API available."""
        return {
            "ok": False,
            "error": "INTERFACE_ONLY: No official GitHub Copilot API available"
        }
    
    def cancel(self, request_id: str) -> dict[str, Any]:
        """No official Copilot cancellation API available."""
        return {
            "ok": False,
            "error": "INTERFACE_ONLY: No official GitHub Copilot API available"
        }
    
    def health(self) -> dict[str, Any]:
        """No official Copilot health check available."""
        return {
            "provider_id": self.provider_id,
            "healthy": False,
            "status": "INTERFACE_ONLY",
            "error": "No official GitHub Copilot public API available"
        }


def create_copilot_provider_record() -> ProviderRecord:
    """Create a ProviderRecord for GitHub Copilot (interface only)."""
    return ProviderRecord(
        provider_id="copilot",
        provider_family="github_copilot",
        display_name="GitHub Copilot",
        description="GitHub Copilot - INTERFACE_ONLY: No official public API currently available",
        status="INTERFACE_ONLY",
        authenticated=False,
        local_or_remote="unknown",
        endpoint="",
        requires_auth=True,
        requires_network=True,
        supports_streaming=False,
        supports_tool_calling=False,
        supports_vision=False,
        supports_audio_input=False,
        supports_audio_output=False,
        supports_structured_output=False,
        api_key_configured=False,
        capabilities={},
        limitations="INTERFACE_ONLY: No official GitHub Copilot public API available. Requires official GitHub integration when released."
    )