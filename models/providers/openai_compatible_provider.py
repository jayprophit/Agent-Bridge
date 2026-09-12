"""OpenAICompatibleProvider adapter (v0.7). Generic OpenAI-compatible endpoints.

This adapter works with any OpenAI-compatible API endpoint, including:
- Local LLM servers (LM Studio, LocalAI, text-generation-webui)
- Custom OpenAI-compatible proxies
- Alternative model providers with OpenAI-compatible APIs
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any

from models.provider_adapter import ProviderAdapter
from models.provider_registry import (
    AUTH_REQUIRED, AUTH_FAILED, NOT_CONFIGURED, OFFLINE,
    OPENAI_COMPATIBLE, PROVIDER_AVAILABLE, PROVIDER_UNAVAILABLE, ProviderRecord
)


class OpenAICompatibleProvider(ProviderAdapter):
    """Provider adapter for OpenAI-compatible endpoints."""
    
    provider_id = "openai_compatible"
    provider_family = OPENAI_COMPATIBLE
    
    def __init__(self, endpoint: str = "", api_key: str = ""):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self._cached_models: list[dict] = []
    
    def discover(self) -> dict[str, Any]:
        """Discover available models from the OpenAI-compatible endpoint."""
        if not self.endpoint:
            return {
                "provider_id": self.provider_id,
                "endpoint": self.endpoint,
                "models": [],
                "error": "Endpoint not configured"
            }
        
        try:
            response = self._openai_compatible_request("GET", "/models")
            if response and "data" in response:
                self._cached_models = response["data"]
                return {
                    "provider_id": self.provider_id,
                    "provider_family": self.provider_family,
                    "endpoint": self.endpoint,
                    "models": self._cached_models,
                    "model_count": len(self._cached_models)
                }
            return {
                "provider_id": self.provider_id,
                "endpoint": self.endpoint,
                "models": [],
                "error": "no models returned"
            }
        except Exception as e:
            return {
                "provider_id": self.provider_id,
                "endpoint": self.endpoint,
                "models": [],
                "error": str(e)[:200]
            }
    
    def authenticate(self, credentials: dict[str, Any] | None = None) -> dict[str, Any]:
        """Authenticate with the OpenAI-compatible endpoint."""
        endpoint = credentials.get("endpoint") if credentials else self.endpoint
        api_key = credentials.get("api_key") if credentials else self.api_key
        
        if not endpoint:
            return {
                "provider_id": self.provider_id,
                "authenticated": False,
                "error": "Endpoint not provided"
            }
        
        self.endpoint = endpoint
        self.api_key = api_key or ""
        
        # Test authentication by listing models
        try:
            response = self._openai_compatible_request("GET", "/models")
            return {
                "provider_id": self.provider_id,
                "authenticated": True,
                "note": "Endpoint validated"
            }
        except Exception as e:
            return {
                "provider_id": self.provider_id,
                "authenticated": False,
                "error": str(e)[:200]
            }
    
    def list_models(self) -> list[dict[str, Any]]:
        """List all available models."""
        if not self._cached_models:
            self.discover()
        return self._cached_models
    
    def model_info(self, model_id: str) -> dict[str, Any]:
        """Get detailed information about a specific model."""
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
        """Report provider capabilities."""
        # Determine if local or remote based on endpoint
        local_or_remote = "local" if any(
            host in self.endpoint.lower()
            for host in ("localhost", "127.0.0.1", "0.0.0.0", "::1")
        ) else "remote"
        
        return {
            "provider_id": self.provider_id,
            "provider_family": self.provider_family,
            "supports_streaming": True,  # Most OpenAI-compatible endpoints support streaming
            "supports_tool_calling": True,  # Depends on specific model/endpoint
            "supports_vision": True,  # Depends on specific model/endpoint
            "supports_audio_input": False,  # Typically not supported
            "supports_audio_output": False,  # Typically not supported
            "supports_structured_output": True,  # Depends on specific model/endpoint
            "local_or_remote": local_or_remote,
            "requires_network": local_or_remote == "remote",
            "requires_auth": bool(self.api_key)
        }
    
    def context_limit(self, model_id: str) -> int:
        """Get context window size for a model."""
        # OpenAI-compatible endpoints may not provide this info
        # Return 0 to indicate unknown
        return 0
    
    def generate(self, model_id: str, messages: list[dict[str, Any]],
                **kwargs) -> dict[str, Any]:
        """Generate a completion."""
        try:
            payload = {
                "model": model_id,
                "messages": messages,
                **kwargs
            }
            response = self._openai_compatible_request("POST", "/chat/completions", payload)
            
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
                "error": "invalid response",
                "response": response
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"generation failed: {e}"
            }
    
    def stream(self, model_id: str, messages: list[dict[str, Any]],
               **kwargs):
        """Stream a completion (generator)."""
        try:
            payload = {
                "model": model_id,
                "messages": messages,
                "stream": True,
                **kwargs
            }
            
            # For streaming, we'd need to handle SSE
            # This is a simplified version
            response = self._openai_compatible_request("POST", "/chat/completions", payload)
            
            if response and "choices" in response and response["choices"]:
                yield response["choices"][0].get("message", {}).get("content", "")
            else:
                yield ""
        except Exception as e:
            yield f"Error: {e}"
    
    def tool_call(self, model_id: str, messages: list[dict[str, Any]],
                  tools: list[dict[str, Any]], **kwargs) -> dict[str, Any]:
        """Generate a tool-calling completion."""
        try:
            payload = {
                "model": model_id,
                "messages": messages,
                "tools": tools,
                **kwargs
            }
            response = self._openai_compatible_request("POST", "/chat/completions", payload)
            
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
                "error": "invalid response",
                "response": response
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"tool call failed: {e}"
            }
    
    def cancel(self, request_id: str) -> dict[str, Any]:
        """Cancel an in-progress request."""
        return {
            "ok": False,
            "error": "Request cancellation not supported"
        }
    
    def health(self) -> dict[str, Any]:
        """Check provider health."""
        if not self.endpoint:
            return {
                "provider_id": self.provider_id,
                "healthy": False,
                "status": NOT_CONFIGURED,
                "endpoint": self.endpoint,
                "error": "Endpoint not configured"
            }
        
        try:
            response = self._openai_compatible_request("GET", "/models")
            return {
                "provider_id": self.provider_id,
                "healthy": True,
                "status": PROVIDER_AVAILABLE,
                "endpoint": self.endpoint,
                "model_count": len(response.get("data", []))
            }
        except Exception as e:
            return {
                "provider_id": self.provider_id,
                "healthy": False,
                "status": PROVIDER_UNAVAILABLE,
                "endpoint": self.endpoint,
                "error": str(e)[:200]
            }
    
    def _openai_compatible_request(self, method: str, path: str,
                                   data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make an HTTP request to the OpenAI-compatible endpoint."""
        url = f"{self.endpoint}{path}"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
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


def create_openai_compatible_provider_record(endpoint: str = "",
                                             api_key: str = "") -> ProviderRecord:
    """Create a ProviderRecord for an OpenAI-compatible endpoint."""
    local_or_remote = "local" if any(
        host in endpoint.lower()
        for host in ("localhost", "127.0.0.1", "0.0.0.0", "::1")
    ) else "remote" if endpoint else "unknown"
    
    return ProviderRecord(
        provider_id="openai_compatible",
        provider_family=OPENAI_COMPATIBLE,
        display_name="OpenAI-Compatible",
        description="Generic OpenAI-compatible API endpoint (LM Studio, LocalAI, etc.)",
        status=NOT_CONFIGURED if endpoint else NOT_CONFIGURED,
        authenticated=False,
        local_or_remote=local_or_remote,
        endpoint=endpoint,
        requires_auth=bool(api_key),
        requires_network=local_or_remote == "remote",
        supports_streaming=True,
        supports_tool_calling=True,
        supports_vision=True,
        supports_audio_input=False,
        supports_audio_output=False,
        supports_structured_output=True,
        api_key_configured=bool(api_key),
        capabilities={
            "streaming": True,
            "tool_calling": True,
            "vision": True,
            "structured_output": True
        },
        limitations="Requires OpenAI-compatible endpoint configuration"
    )