"""llama.cpp provider adapter (v0.7). Uses OpenAI-compatible adapter.

llama.cpp provides a local OpenAI-compatible API endpoint for running
local models. We use the OpenAICompatibleProvider with llama.cpp-specific
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


class LlamaCppProvider(OpenAICompatibleProvider):
    """Provider adapter for llama.cpp using OpenAI-compatible interface."""
    
    provider_id = "llama_cpp"
    provider_family = "llama_cpp"
    
    def __init__(self, endpoint: str = "http://localhost:8080"):
        # llama.cpp server typically runs on localhost:8080
        super().__init__(endpoint=endpoint, api_key="")


def create_llama_cpp_provider_record(endpoint: str = "http://localhost:8080") -> ProviderRecord:
    """Create a ProviderRecord for llama.cpp."""
    record = create_openai_compatible_provider_record(endpoint, "")
    record.provider_id = "llama_cpp"
    record.provider_family = "llama_cpp"
    record.display_name = "llama.cpp"
    record.description = "llama.cpp local OpenAI-compatible API endpoint"
    record.status = NOT_CONFIGURED
    record.requires_auth = False
    record.local_or_remote = "local"
    record.limitations = "Requires llama.cpp server to be installed and running locally"
    return record