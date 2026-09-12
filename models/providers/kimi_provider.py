"""Kimi (Moonshot) provider adapter (v0.7). Uses OpenAI-compatible adapter.

Moonshot AI's Kimi API uses an OpenAI-compatible interface, so we use the
OpenAICompatibleProvider with Kimi-specific configuration.
"""
from __future__ import annotations

from models.providers.openai_compatible_provider import (
    OpenAICompatibleProvider,
    create_openai_compatible_provider_record
)
from models.provider_registry import (
    AUTH_REQUIRED, NOT_CONFIGURED, ProviderRecord
)


class KimiProvider(OpenAICompatibleProvider):
    """Provider adapter for Kimi (Moonshot AI) using OpenAI-compatible interface."""
    
    provider_id = "kimi"
    provider_family = "moonshot"
    
    def __init__(self, api_key: str = "", base_url: str = "https://api.moonshot.cn"):
        # Kimi uses OpenAI-compatible API
        super().__init__(endpoint=base_url, api_key=api_key)


def create_kimi_provider_record(api_key: str = "",
                                base_url: str = "https://api.moonshot.cn") -> ProviderRecord:
    """Create a ProviderRecord for Kimi."""
    record = create_openai_compatible_provider_record(base_url, api_key)
    record.provider_id = "kimi"
    record.provider_family = "moonshot"
    record.display_name = "Kimi"
    record.description = "Moonshot AI Kimi API for Kimi models"
    record.status = AUTH_REQUIRED if not api_key else NOT_CONFIGURED
    record.limitations = "Requires Kimi API key and internet connection"
    return record