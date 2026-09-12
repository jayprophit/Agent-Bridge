"""LM Studio provider adapter (v0.7). Uses OpenAI-compatible adapter.

LM Studio provides a local OpenAI-compatible API endpoint for running
local models. We use the OpenAICompatibleProvider with LM Studio-specific
configuration.
"""
from __future__ import annotations

from models.providers.openai_compatible_provider import (
    OpenAICompatibleProvider,
    create_openai_compatible_provider_record
)
from models.provider_registry import (
    NOT_CONFIGURED, OPENAI_COMPATIBLE, ProviderRecord
)


class LMStudioProvider(OpenAICompatibleProvider):
    """Provider adapter for LM Studio using OpenAI-compatible interface."""
    
    provider_id = "lm_studio"
    provider_family = "lm_studio"
    
    def __init__(self, endpoint: str = "http://localhost:1234"):
        # LM Studio typically runs on localhost:1234
        super().__init__(endpoint=endpoint, api_key="")


def create_lm_studio_provider_record(endpoint: str = "http://localhost:1234") -> ProviderRecord:
    """Create a ProviderRecord for LM Studio."""
    record = create_openai_compatible_provider_record(endpoint, "")
    record.provider_id = "lm_studio"
    record.provider_family = "lm_studio"
    record.display_name = "LM Studio"
    record.description = "LM Studio local OpenAI-compatible API endpoint"
    record.status = NOT_CONFIGURED
    record.requires_auth = False
    record.local_or_remote = "local"
    record.limitations = "Requires LM Studio to be installed and running locally"
    return record