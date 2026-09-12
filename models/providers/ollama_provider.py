"""OllamaProvider adapter (v0.7). Local Ollama runtime integration.

Ollama is a local model runtime that can run various models (Llama, Qwen, etc.).
This adapter provides the interface to Ollama's HTTP API.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any

from models.provider_adapter import ProviderAdapter
from models.provider_registry import (
    AUTH_REQUIRED, NOT_CONFIGURED, OFFLINE, OLLAMA,
    PROVIDER_AVAILABLE, PROVIDER_UNAVAILABLE, ProviderRecord
)
from models.model_registry import MODEL_AVAILABLE, MODEL_UNAVAILABLE, ModelRecord


class OllamaProvider(ProviderAdapter):
    """Provider adapter for local Ollama runtime."""
    
    provider_id = "ollama"
    provider_family = OLLAMA
    
    def __init__(self, endpoint: str = "http://localhost:11434"):
        self.endpoint = endpoint.rstrip("/")
        self._cached_models: list[dict] = []
    
    def discover(self) -> dict[str, Any]:
        """Discover available models from Ollama."""
        try:
            response = self._ollama_request("GET", "/api/tags")
            if response and "models" in response:
                self._cached_models = response["models"]
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
        """Ollama typically doesn't require authentication."""
        # Check if Ollama is reachable
        try:
            self._ollama_request("GET", "/api/tags")
            return {
                "provider_id": self.provider_id,
                "authenticated": True,
                "note": "Ollama typically runs without authentication"
            }
        except Exception as e:
            return {
                "provider_id": self.provider_id,
                "authenticated": False,
                "error": str(e)[:200]
            }
    
    def list_models(self) -> list[dict[str, Any]]:
        """List all available Ollama models."""
        if not self._cached_models:
            self.discover()
        return self._cached_models
    
    def model_info(self, model_id: str) -> dict[str, Any]:
        """Get detailed information about a specific Ollama model."""
        try:
            response = self._ollama_request("POST", "/api/show", 
                                           {"name": model_id})
            return {
                "model_id": model_id,
                "available": True,
                "info": response
            }
        except Exception as e:
            return {
                "model_id": model_id,
                "available": False,
                "error": str(e)[:200]
            }
    
    def capabilities(self) -> dict[str, Any]:
        """Report Ollama provider capabilities."""
        return {
            "provider_id": self.provider_id,
            "provider_family": self.provider_family,
            "supports_streaming": True,
            "supports_tool_calling": True,  # Depends on model
            "supports_vision": True,  # Depends on model
            "supports_audio_input": False,
            "supports_audio_output": False,
            "supports_structured_output": True,  # Depends on model
            "supports_think_control": True,  # think True/False/None(omit)
            "local_or_remote": "local",
            "requires_network": False,  # Local HTTP
            "requires_auth": False
        }
    
    def context_limit(self, model_id: str) -> int:
        """Get context window size for an Ollama model."""
        try:
            info = self.model_info(model_id)
            if "info" in info:
                # Ollama model info may contain context window
                details = info["info"]
                if isinstance(details, dict):
                    # Try to extract context from model details
                    return details.get("context_length", 0) or \
                           details.get("context_window", 0) or 0
        except Exception:
            pass
        return 0
    
    def generate(self, model_id: str, messages: list[dict[str, Any]],
                 **kwargs) -> dict[str, Any]:
        """Generate a completion using Ollama.

        think=True/False is forwarded ONLY when explicitly passed (never
        blindly: older models reject unknown fields). think=False keeps
        reasoning models (e.g. qwen3) answering in content for tool use.
        """
        try:
            think = kwargs.pop("think", None)
            payload = {
                "model": model_id,
                "messages": messages,
                "stream": False,
                **kwargs
            }
            if think is not None:
                payload["think"] = bool(think)
            response = self._ollama_request("POST", "/api/chat", payload)

            if response and "message" in response:
                return {
                    "ok": True,
                    "content": response["message"].get("content", ""),
                    "model": model_id,
                    "done": response.get("done", False),
                    "think_requested": think,
                    "metadata": {
                        "total_duration": response.get("total_duration"),
                        "load_duration": response.get("load_duration"),
                        "prompt_eval_count": response.get("prompt_eval_count"),
                        "eval_count": response.get("eval_count"),
                        "thinking_chars": len(
                            response["message"].get("thinking") or ""),
                    }
                }
            return {
                "ok": False,
                "error": "invalid response from Ollama",
                "response": response
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"Ollama generation failed: {e}"
            }
    
    def stream(self, model_id: str, messages: list[dict[str, Any]],
                **kwargs):
        """Stream a completion from Ollama (generator). think= is
        forwarded only when explicitly passed (see generate)."""
        try:
            think = kwargs.pop("think", None)
            payload = {
                "model": model_id,
                "messages": messages,
                "stream": True,
                **kwargs
            }
            if think is not None:
                payload["think"] = bool(think)
            
            # For streaming, we'd need to handle streaming HTTP
            # This is a simplified version
            response = self._ollama_request("POST", "/api/chat", payload)
            
            if response and "message" in response:
                yield response["message"].get("content", "")
            else:
                yield ""
        except Exception as e:
            yield f"Error: {e}"
    
    def tool_call(self, model_id: str, messages: list[dict[str, Any]],
                  tools: list[dict[str, Any]], **kwargs) -> dict[str, Any]:
        """Generate a tool-calling completion using Ollama."""
        # Ollama supports tool calling through the 'tools' parameter
        try:
            think = kwargs.pop("think", None)
            payload = {
                "model": model_id,
                "messages": messages,
                "tools": tools,
                "stream": False,
                **kwargs
            }
            if think is not None:
                payload["think"] = bool(think)
            response = self._ollama_request("POST", "/api/chat", payload)
            
            if response and "message" in response:
                message = response["message"]
                return {
                    "ok": True,
                    "content": message.get("content", ""),
                    "tool_calls": message.get("tool_calls", []),
                    "model": model_id,
                    "metadata": {
                        "total_duration": response.get("total_duration"),
                        "eval_count": response.get("eval_count")
                    }
                }
            return {
                "ok": False,
                "error": "invalid response from Ollama",
                "response": response
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"Ollama tool call failed: {e}"
            }
    
    def cancel(self, request_id: str) -> dict[str, Any]:
        """Cancel an in-progress Ollama request."""
        # Ollama doesn't have a built-in cancel API
        return {
            "ok": False,
            "error": "Ollama does not support request cancellation"
        }
    
    def health(self) -> dict[str, Any]:
        """Check Ollama health."""
        try:
            response = self._ollama_request("GET", "/api/tags")
            return {
                "provider_id": self.provider_id,
                "healthy": True,
                "status": PROVIDER_AVAILABLE,
                "endpoint": self.endpoint,
                "model_count": len(response.get("models", []))
            }
        except Exception as e:
            return {
                "provider_id": self.provider_id,
                "healthy": False,
                "status": PROVIDER_UNAVAILABLE,
                "endpoint": self.endpoint,
                "error": str(e)[:200]
            }
    
    def _ollama_request(self, method: str, path: str,
                       data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make an HTTP request to Ollama."""
        url = f"{self.endpoint}{path}"
        
        if method == "GET":
            req = urllib.request.Request(url)
            timeout = 30  # Short timeout for discovery/health checks
        else:
            req = urllib.request.Request(url, 
                                       data=json.dumps(data).encode("utf-8"),
                                       headers={"Content-Type": "application/json"})
            timeout = 120  # Longer timeout for model generation
        
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.readable() else ""
            raise Exception(f"HTTP {e.code}: {error_body}")
        except urllib.error.URLError as e:
            raise Exception(f"Connection failed: {e.reason}")
        except Exception as e:
            raise Exception(f"Request failed: {e}")


def create_ollama_provider_record(endpoint: str = "http://localhost:11434") -> ProviderRecord:
    """Create a ProviderRecord for Ollama."""
    return ProviderRecord(
        provider_id="ollama",
        provider_family=OLLAMA,
        display_name="Ollama",
        description="Local model runtime for running LLMs (Llama, Qwen, etc.)",
        status=NOT_CONFIGURED,
        authenticated=False,
        local_or_remote="local",
        endpoint=endpoint,
        requires_auth=False,
        requires_network=False,
        supports_streaming=True,
        supports_tool_calling=True,
        supports_vision=True,
        supports_audio_input=False,
        supports_audio_output=False,
        supports_structured_output=True,
        api_key_configured=False,
        capabilities={
            "streaming": True,
            "tool_calling": True,
            "vision": True,
            "structured_output": True
        },
        limitations="Requires Ollama to be installed and running locally"
    )