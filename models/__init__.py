"""Universal Model/Provider Registry (v0.7). Model-agnostic runtime foundation.

This module provides the core abstractions for:
- ModelRegistry: catalog of available AI models with capabilities
- ProviderRegistry: catalog of model providers (Ollama, OpenAI, etc.)
- ModelRouter: task-aware model selection and routing
- Provider adapters: pluggable provider interfaces

The runtime is no longer tied to any specific model or provider.
Models are replaceable reasoning providers; providers are swappable backends.
"""
from __future__ import annotations

from models.model_registry import ModelRegistry, ModelRecord
from models.provider_registry import ProviderRegistry, ProviderRecord
from models.model_router import ModelRouter, RoutingDecision
from models.provider_adapter import ProviderAdapter

__all__ = [
    "ModelRegistry",
    "ModelRecord", 
    "ProviderRegistry",
    "ProviderRecord",
    "ModelRouter",
    "RoutingDecision",
    "ProviderAdapter",
]