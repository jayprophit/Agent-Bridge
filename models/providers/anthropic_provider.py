"""AnthropicProvider adapter (v0.7). Anthropic Claude API integration.

Anthropic API provides access to Claude models (Claude 3, etc.).
This adapter provides the interface to Anthropic's REST API.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any

from models.provider_adapter import ProviderAdapter
from models.provider_registry import (
    AUTH_REQUIRED, AUTH_FAILED, NOT_CONFIGURED, OFFLINE,
    ANTHROPIC, PROVIDER_AVAILABLE, PROVIDER_UNAVAILABLE, ProviderRecord
)


class AnthropicProvider(ProviderAdapter):
    """Provider adapter for Anthropic Claude API."""
    
    provider_id = "anthropic"
    provider_family = ANTHROPIC
    
    def __init__(self, api_key: str = "", base_url: str = "https://api.anthropic.com"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._cached_models: list[dict] = []
    
    def discover(self) -> dict[str, Any]:
        """Discover available models from Anthropic."""
        if not self.api_key:
            return {
                "provider_id": self.provider_id,
                "endpoint": self.base_url,
                "models": [],
                "error": "API key not configured"
            }
        
        try:
            # Anthropic doesn't have a public models list endpoint
            # We'll return known Claude models
            known_models = [
                {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus"},
                {"id": "claude-3-sonnet-20240229", "name": "Claude 3 Sonnet"},
                {"id": "claude-3-haiku-20240307", "name": "Claude 3 Haiku"},
            ]
            self._cached_models = known_models
            return {
                "provider_id": self.provider_id,
                "provider_family": self.provider_family,
                "endpoint": self.base_url,
                "models": self._cached_models,
                "model_count": len(self._cached_models),
                "note": "Anthropic does not provide a public models endpoint"
            }
        except Exception as e:
            return {
                "provider_id": self.provider_id,
                "endpoint": self.base_url,
                "models": [],
                "error": str(e)[:200]
            }
    
    def authenticate(self, credentials: dict[str, Any] | None = None) -> dict[str, Any]:
        """Authenticate with Anthropic using API key."""
        api_key = credentials.get("api_key") if credentials else self.api_key
        
        if not api_key:
            return {
                "provider_id": self.provider_id,
                "authenticated": False,
                "error": "API key not provided"
            }
        
        self.api_key = api_key
        
        # Test authentication with a minimal request
        try:
            payload = {
                "model": "claude-3-haiku-20240307",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "test"}]
            }
            self._anthropic_request("POST", "/v1/messages", payload)
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
        """List all available Anthropic models."""
        if not self._cached_models:
            self.discover()
        return self._cached_models
    
    def model_info(self, model_id: str) -> dict[str, Any]:
        """Get detailed information about a specific Anthropic model."""
        # Anthropic doesn't have a detailed model info endpoint
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
        """Report Anthropic provider capabilities."""
        return {
            "provider_id": self.provider_id,
            "provider_family": self.provider_family,
            "supports_streaming": True,
            "supports_tool_calling": True,
            "supports_vision": True,  # Claude 3 has vision
            "supports_audio_input": False,
            "supports_audio_output": False,
            "supports_structured_output": True,
            "local_or_remote": "remote",
            "requires_network": True,
            "requires_auth": True
        }
    
    def context_limit(self, model_id: str) -> int:
        """Get context window size for an Anthropic model."""
        # Claude 3 context limits
        context_limits = {
            "claude-3-opus-20240229": 200000,
            "claude-3-sonnet-20240229": 200000,
            "claude-3-haiku-20240307": 200000,
        }
        return context_limits.get(model_id, 0)
    
    def generate(self, model_id: str, messages: list[dict[str, Any]],
                **kwargs) -> dict[str, Any]:
        """Generate a completion using Anthropic."""
        try:
            # Convert OpenAI-style messages to Anthropic format
            anthropic_messages = self._convert_messages(messages)
            
            payload = {
                "model": model_id,
                "messages": anthropic_messages,
                "max_tokens": kwargs.get("max_tokens", 1024),
                **{k: v for k, v in kwargs.items() if k != "max_tokens"}
            }
            response = self._anthropic_request("POST", "/v1/messages", payload)
            
            if response and "content" in response:
                content = response["content"]
                text_content = ""
                if isinstance(content, list) and content:
                    text_content = content[0].get("text", "")
                
                return {
                    "ok": True,
                    "content": text_content,
                    "model": response.get("model", model_id),
                    "stop_reason": response.get("stop_reason"),
                    "metadata": {
                        "usage": response.get("usage", {}),
                        "id": response.get("id")
                    }
                }
            return {
                "ok": False,
                "error": "invalid response from Anthropic",
                "response": response
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"Anthropic generation failed: {e}"
            }
    
    def stream(self, model_id: str, messages: list[dict[str, Any]],
               **kwargs):
        """Stream a completion from Anthropic (generator)."""
        try:
            anthropic_messages = self._convert_messages(messages)
            payload = {
                "model": model_id,
                "messages": anthropic_messages,
                "max_tokens": kwargs.get("max_tokens", 1024),
                "stream": True,
                **{k: v for k, v in kwargs.items() if k not in ("max_tokens", "stream")}
            }
            
            # For streaming, we'd need to handle SSE
            # This is a simplified version
            response = self._anthropic_request("POST", "/v1/messages", payload)
            
            if response and "content" in response:
                content = response["content"]
                if isinstance(content, list) and content:
                    yield content[0].get("text", "")
            else:
                yield ""
        except Exception as e:
            yield f"Error: {e}"
    
    def tool_call(self, model_id: str, messages: list[dict[str, Any]],
                  tools: list[dict[str, Any]], **kwargs) -> dict[str, Any]:
        """Generate a tool-calling completion using Anthropic."""
        try:
            anthropic_messages = self._convert_messages(messages)
            
            # Convert tools to Anthropic format
            anthropic_tools = self._convert_tools(tools)
            
            payload = {
                "model": model_id,
                "messages": anthropic_messages,
                "tools": anthropic_tools,
                "max_tokens": kwargs.get("max_tokens", 1024),
                **{k: v for k, v in kwargs.items() if k != "max_tokens"}
            }
            response = self._anthropic_request("POST", "/v1/messages", payload)
            
            if response and "content" in response:
                content = response["content"]
                text_content = ""
                tool_calls = []
                
                if isinstance(content, list):
                    for block in content:
                        if block.get("type") == "text":
                            text_content += block.get("text", "")
                        elif block.get("type") == "tool_use":
                            tool_calls.append({
                                "id": block.get("id"),
                                "name": block.get("name"),
                                "input": block.get("input", {})
                            })
                
                return {
                    "ok": True,
                    "content": text_content,
                    "tool_calls": tool_calls,
                    "model": response.get("model", model_id),
                    "stop_reason": response.get("stop_reason"),
                    "metadata": {
                        "usage": response.get("usage", {}),
                        "id": response.get("id")
                    }
                }
            return {
                "ok": False,
                "error": "invalid response from Anthropic",
                "response": response
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"Anthropic tool call failed: {e}"
            }
    
    def cancel(self, request_id: str) -> dict[str, Any]:
        """Cancel an in-progress Anthropic request."""
        return {
            "ok": False,
            "error": "Anthropic does not support request cancellation"
        }
    
    def health(self) -> dict[str, Any]:
        """Check Anthropic health."""
        if not self.api_key:
            return {
                "provider_id": self.provider_id,
                "healthy": False,
                "status": AUTH_REQUIRED,
                "endpoint": self.base_url,
                "error": "API key not configured"
            }
        
        try:
            # Test with a minimal request
            payload = {
                "model": "claude-3-haiku-20240307",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "test"}]
            }
            self._anthropic_request("POST", "/v1/messages", payload)
            return {
                "provider_id": self.provider_id,
                "healthy": True,
                "status": PROVIDER_AVAILABLE,
                "endpoint": self.base_url
            }
        except Exception as e:
            return {
                "provider_id": self.provider_id,
                "healthy": False,
                "status": PROVIDER_UNAVAILABLE,
                "endpoint": self.base_url,
                "error": str(e)[:200]
            }
    
    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI-style messages to Anthropic format."""
        anthropic_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                # Anthropic puts system content in a special field
                # For now, we'll convert to user message
                anthropic_messages.append({
                    "role": "user",
                    "content": f"System: {content}"
                })
            else:
                anthropic_messages.append({
                    "role": role,
                    "content": content
                })
        return anthropic_messages
    
    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert OpenAI-style tools to Anthropic format."""
        anthropic_tools = []
        for tool in tools:
            function = tool.get("function", {})
            anthropic_tools.append({
                "name": function.get("name"),
                "description": function.get("description", ""),
                "input_schema": function.get("parameters", {})
            })
        return anthropic_tools
    
    def _anthropic_request(self, method: str, path: str,
                          data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make an HTTP request to Anthropic."""
        url = f"{self.base_url}{path}"
        
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
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


def create_anthropic_provider_record(api_key: str = "",
                                     base_url: str = "https://api.anthropic.com") -> ProviderRecord:
    """Create a ProviderRecord for Anthropic."""
    return ProviderRecord(
        provider_id="anthropic",
        provider_family=ANTHROPIC,
        display_name="Anthropic Claude",
        description="Anthropic API for Claude models (Claude 3 Opus, Sonnet, Haiku)",
        status=AUTH_REQUIRED if not api_key else NOT_CONFIGURED,
        authenticated=False,
        local_or_remote="remote",
        endpoint=base_url,
        requires_auth=True,
        requires_network=True,
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
        limitations="Requires Anthropic API key and internet connection"
    )