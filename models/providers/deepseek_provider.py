"""DeepSeek provider adapter (v0.7). Uses OpenAI-compatible adapter.

DeepSeek API uses an OpenAI-compatible interface, so we use the
OpenAICompatibleProvider with DeepSeek-specific configuration.
"""
from __future__ import annotations

from models.providers.openai_compatible_provider import (
    OpenAICompatibleProvider,
    create_openai_compatible_provider_record
)
from models.provider_registry import (
    AUTH_REQUIRED, NOT_CONFIGURED, OPENAI_COMPATIBLE, ProviderRecord
)


class DeepSeekProvider(OpenAICompatibleProvider):
    """Provider adapter for DeepSeek using OpenAI-compatible interface."""
    
    provider_id = "deepseek"
    provider_family = "deepseek"
    
    def __init__(self, api_key: str = "", base_url: str = "https://api.deepseek.com"):
        # DeepSeek uses OpenAI-compatible API
        super().__init__(endpoint=base_url, api_key=api_key)


def create_deepseek_provider_record(api_key: str = "",
                                  base_url: str = "https://api.deepseek.com") -> ProviderRecord:
    """Create a ProviderRecord for DeepSeek."""
    record = create_openai_compatible_provider_record(base_url, api_key)
    record.provider_id = "deepseek"
    record.provider_family = "deepseek"
    record.display_name = "DeepSeek"
    record.description = "DeepSeek API for DeepSeek models (DeepSeek-V2, DeepSeek-Coder, etc.)"
    record.status = AUTH_REQUIRED if not api_key else NOT_CONFIGURED
    record.limitations = "Requires DeepSeek API key and internet connection"
    return record