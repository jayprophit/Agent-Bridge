"""OpenAIProvider adapter (v0.7). OpenAI API integration.

OpenAI API provides access to GPT models (GPT-4, GPT-3.5, etc.).
This adapter provides the interface to OpenAI's REST API.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any

from models.provider_adapter import ProviderAdapter
from models.provider_registry import (
    AUTH_REQUIRED, AUTH_FAILED, NOT_CONFIGURED, OFFLINE,
    OPENAI_API, PROVIDER_AVAILABLE, PROVIDER_UNAVAILABLE, ProviderRecord
)


class OpenAIProvider(ProviderAdapter):
    """Provider adapter for OpenAI API."""
    
    provider_id = "openai"
    provider_family = OPENAI_API
    
    def __init__(self, api_key: str = "", base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._cached_models: list[dict] = []
    
    def discover(self) -> dict[str, Any]:
        """Discover available models from OpenAI."""
        if not self.api_key:
            return {
                "provider_id": self.provider_id,
                "endpoint": self.base_url,
                "models": [],
                "error": "API key not configured"
            }
        
        try:
            response = self._openai_request("GET", "/models")
            if response and "data" in response:
                self._cached_models = response["data"]
                return {
                    "provider_id": self.provider_id,
                    "provider_family": self.provider_family,
                    "endpoint": self.base_url,
                    "models": self._cached_models,
                    "model_count": len(self._cached_models)
                }
            return {
                "provider_id": self.provider_id,
                "endpoint": self.base_url,
                "models": [],
                "error": "no models returned"
            }
        except Exception as e:
            return {
                "provider_id": self.provider_id,
                "endpoint": self.base_url,
                "models": [],
                "error": str(e)[:200]
            }
    
    def authenticate(self, credentials: dict[str, Any] | None = None) -> dict[str, Any]:
        """Authenticate with OpenAI using API key."""
        api_key = credentials.get("api_key") if credentials else self.api_key
        
        if not api_key:
            return {
                "provider_id": self.provider_id,
                "authenticated": False,
                "error": "API key not provided"
            }
        
        self.api_key = api_key
        
        # Test authentication by listing models
        try:
            response = self._openai_request("GET", "/models")
            return {
                "provider_id": self.provider_id,
                "authenticated": True,
                "note": "API key validated"
            }
        except Exception as e:
            return {
                "provider_id": self.provider_id,
                "authenticated": False,
                "error": str(e)[:200]
            }
    
    def list_models(self) -> list[dict[str, Any]]:
        """List all available OpenAI models."""
        if not self._cached_models:
            self.discover()
        return self._cached_models
    
    def model_info(self, model_id: str) -> dict[str, Any]:
        """Get detailed information about a specific OpenAI model."""
        # OpenAI doesn't have a detailed model info endpoint
        # Return basic info from the models list
        for model in self._cached_models:
            if model.get("id") == model_id:
                return {
                    "model_id": model_id,
                    "available": True,
                    "info": model
                }
        return {
            "model_id": model_id,
            "available": False,
            "error": "model not found"
        }
    
    def capabilities(self) -> dict[str, Any]:
        """Report OpenAI provider capabilities."""
        return {
            "provider_id": self.provider_id,
            "provider_family": self.provider_family,
            "supports_streaming": True,
            "supports_tool_calling": True,
            "supports_vision": True,  # GPT-4 Vision
            "supports_audio_input": True,  # Whisper
            "supports_audio_output": True,  # TTS
            "supports_structured_output": True,
            "local_or_remote": "remote",
            "requires_network": True,
            "requires_auth": True
        }
    
    def context_limit(self, model_id: str) -> int:
        """Get context window size for an OpenAI model."""
        # Context limits vary by model
        # GPT-4: 8192, 32768, or higher depending on variant
        # GPT-3.5: 4096 or 16384
        context_limits = {
            "gpt-4": 8192,
            "gpt-4-32k": 32768,
            "gpt-4-turbo": 128000,
            "gpt-4-turbo-preview": 128000,
            "gpt-3.5-turbo": 4096,
            "gpt-3.5-turbo-16k": 16384,
        }
        return context_limits.get(model_id, 0)
    
    def generate(self, model_id: str, messages: list[dict[str, Any]],
                **kwargs) -> dict[str, Any]:
        """Generate a completion using OpenAI."""
        try:
            payload = {
                "model": model_id,
                "messages": messages,
                **kwargs
            }
            response = self._openai_request("POST", "/chat/completions", payload)
            
            if response and "choices" in response and response["choices"]:
                choice = response["choices"][0]
                return {
                    "ok": True,
                    "content": choice.get("message", {}).get("content", ""),
                    "model": response.get("model", model_id),
                    "finish_reason": choice.get("finish_reason"),
                    "metadata": {
                        "usage": response.get("usage", {}),
                        "id": response.get("id")
                    }
                }
            return {
                "ok": False,
                "error": "invalid response from OpenAI",
                "response": response
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"OpenAI generation failed: {e}"
            }
    
    def stream(self, model_id: str, messages: list[dict[str, Any]],
               **kwargs):
        """Stream a completion from OpenAI (generator)."""
        try:
            payload = {
                "model": model_id,
                "messages": messages,
                "stream": True,
                **kwargs
            }
            
            # For streaming, we'd need to handle SSE
            # This is a simplified version
            response = self._openai_request("POST", "/chat/completions", payload)
            
            if response and "choices" in response and response["choices"]:
                yield response["choices"][0].get("message", {}).get("content", "")
            else:
                yield ""
        except Exception as e:
            yield f"Error: {e}"
    
    def tool_call(self, model_id: str, messages: list[dict[str, Any]],
                  tools: list[dict[str, Any]], **kwargs) -> dict[str, Any]:
        """Generate a tool-calling completion using OpenAI."""
        try:
            payload = {
                "model": model_id,
                "messages": messages,
                "tools": tools,
                **kwargs
            }
            response = self._openai_request("POST", "/chat/completions", payload)
            
            if response and "choices" in response and response["choices"]:
                choice = response["choices"][0]
                message = choice.get("message", {})
                return {
                    "ok": True,
                    "content": message.get("content", ""),
                    "tool_calls": message.get("tool_calls", []),
                    "model": response.get("model", model_id),
                    "finish_reason": choice.get("finish_reason"),
                    "metadata": {
                        "usage": response.get("usage", {}),
                        "id": response.get("id")
                    }
                }
            return {
                "ok": False,
                "error": "invalid response from OpenAI",
                "response": response
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"OpenAI tool call failed: {e}"
            }
    
    def cancel(self, request_id: str) -> dict[str, Any]:
        """Cancel an in-progress OpenAI request."""
        # OpenAI doesn't have a built-in cancel API
        return {
            "ok": False,
            "error": "OpenAI does not support request cancellation"
        }
    
    def health(self) -> dict[str, Any]:
        """Check OpenAI health."""
        if not self.api_key:
            return {
                "provider_id": self.provider_id,
                "healthy": False,
                "status": AUTH_REQUIRED,
                "endpoint": self.base_url,
                "error": "API key not configured"
            }
        
        try:
            response = self._openai_request("GET", "/models")
            return {
                "provider_id": self.provider_id,
                "healthy": True,
                "status": PROVIDER_AVAILABLE,
                "endpoint": self.base_url,
                "model_count": len(response.get("data", []))
            }
        except Exception as e:
            return {
                "provider_id": self.provider_id,
                "healthy": False,
                "status": PROVIDER_UNAVAILABLE,
                "endpoint": self.base_url,
                "error": str(e)[:200]
            }
    
    def _openai_request(self, method: str, path: str,
                       data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make an HTTP request to OpenAI."""
        url = f"{self.base_url}{path}"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        if method == "GET":
            req = urllib.request.Request(url, headers=headers)
        else:
            req = urllib.request.Request(url,
                                       data=json.dumps(data).encode("utf-8"),
                                       headers=headers)
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.readable() else ""
            raise Exception(f"HTTP {e.code}: {error_body}")
        except urllib.error.URLError as e:
            raise Exception(f"Connection failed: {e.reason}")
        except Exception as e:
            raise Exception(f"Request failed: {e}")


def create_openai_provider_record(api_key: str = "",
                                  base_url: str = "https://api.openai.com/v1") -> ProviderRecord:
    """Create a ProviderRecord for OpenAI."""
    return ProviderRecord(
        provider_id="openai",
        provider_family=OPENAI_API,
        display_name="OpenAI",
        description="OpenAI API for GPT models (GPT-4, GPT-3.5, etc.)",
        status=AUTH_REQUIRED if not api_key else NOT_CONFIGURED,
        authenticated=False,
        local_or_remote="remote",
        endpoint=base_url,
        requires_auth=True,
        requires_network=True,
        supports_streaming=True,
        supports_tool_calling=True,
        supports_vision=True,
        supports_audio_input=True,
        supports_audio_output=True,
        supports_structured_output=True,
        api_key_configured=bool(api_key),
        capabilities={
            "streaming": True,
            "tool_calling": True,
            "vision": True,
            "audio_input": True,
            "audio_output": True,
            "structured_output": True
        },
        limitations="Requires OpenAI API key and internet connection"
    )