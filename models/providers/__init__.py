"""Provider adapter implementations (v0.7).

Concrete implementations of ProviderAdapter for various providers:
- OllamaProvider: Local Ollama runtime
- OpenAIProvider: OpenAI API
- AnthropicProvider: Anthropic Claude API
- OpenAICompatibleProvider: Generic OpenAI-compatible endpoints
- DeepSeekProvider: DeepSeek API (uses OpenAI-compatible)
- KimiProvider: Moonshot Kimi API (uses OpenAI-compatible)
- GeminiProvider: Google Gemini API
- LMStudioProvider: LM Studio local API (uses OpenAI-compatible)
- LlamaCppProvider: llama.cpp local API (uses OpenAI-compatible)
- CopilotProvider: GitHub Copilot (INTERFACE_ONLY - no official API)
"""
from __future__ import annotations

from models.providers.ollama_provider import OllamaProvider
from models.providers.openai_provider import OpenAIProvider
from models.providers.anthropic_provider import AnthropicProvider
from models.providers.openai_compatible_provider import OpenAICompatibleProvider
from models.providers.deepseek_provider import DeepSeekProvider
from models.providers.kimi_provider import KimiProvider
from models.providers.gemini_provider import GeminiProvider
from models.providers.lm_studio_provider import LMStudioProvider
from models.providers.llama_cpp_provider import LlamaCppProvider
from models.providers.copilot_provider import CopilotProvider

__all__ = [
    "OllamaProvider",
    "OpenAIProvider", 
    "AnthropicProvider",
    "OpenAICompatibleProvider",
    "DeepSeekProvider",
    "KimiProvider",
    "GeminiProvider",
    "LMStudioProvider",
    "LlamaCppProvider",
    "CopilotProvider",
]