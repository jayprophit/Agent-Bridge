"""Gemini provider adapter (v0.7). Google Gemini API integration.

Google Gemini API provides access to Gemini models (Gemini Pro, Gemini Ultra, etc.).
This adapter provides the interface to Google's REST API.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any

from models.provider_adapter import ProviderAdapter
from models.provider_registry import (
    AUTH_REQUIRED, AUTH_FAILED, NOT_CONFIGURED, OFFLINE,
    PROVIDER_AVAILABLE, PROVIDER_UNAVAILABLE, ProviderRecord
)


class GeminiProvider(ProviderAdapter):
    """Provider adapter for Google Gemini API."""
    
    provider_id = "gemini"
    provider_family = "google"
    
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self._cached_models: list[dict] = []
    
    def discover(self) -> dict[str, Any]:
        """Discover available models from Gemini."""
        if not self.api_key:
            return {
                "provider_id": self.provider_id,
                "models": [],
                "error": "API key not configured"
            }
        
        try:
            # Gemini doesn't have a public models list endpoint like OpenAI
            # We'll return known Gemini models
            known_models = [
                {"id": "gemini-pro", "name": "Gemini Pro"},
                {"id": "gemini-pro-vision", "name": "Gemini Pro Vision"},
                {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro"},
                {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash"},
            ]
            self._cached_models = known_models
            return {
                "provider_id": self.provider_id,
                "provider_family": self.provider_family,
                "models": self._cached_models,
                "model_count": len(self._cached_models),
                "note": "Gemini does not provide a public models endpoint"
            }
        except Exception as e:
            return {
                "provider_id": self.provider_id,
                "models": [],
                "error": str(e)[:200]
            }
    
    def authenticate(self, credentials: dict[str, Any] | None = None) -> dict[str, Any]:
        """Authenticate with Gemini using API key."""
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
            url = f"{self.base_url}/models/gemini-pro:generateContent?key={self.api_key}"
            payload = {"contents": [{"parts": [{"text": "test"}]}]}
            req = urllib.request.Request(url,
                                       data=json.dumps(payload).encode("utf-8"),
                                       headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
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
        """List all available Gemini models."""
        if not self._cached_models:
            self.discover()
        return self._cached_models
    
    def model_info(self, model_id: str) -> dict[str, Any]:
        """Get detailed information about a specific Gemini model."""
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
        """Report Gemini provider capabilities."""
        return {
            "provider_id": self.provider_id,
            "provider_family": self.provider_family,
            "supports_streaming": True,
            "supports_tool_calling": True,
            "supports_vision": True,  # Gemini Pro Vision
            "supports_audio_input": False,
            "supports_audio_output": False,
            "supports_structured_output": True,
            "local_or_remote": "remote",
            "requires_network": True,
            "requires_auth": True
        }
    
    def context_limit(self, model_id: str) -> int:
        """Get context window size for a Gemini model."""
        # Gemini context limits
        context_limits = {
            "gemini-pro": 91728,
            "gemini-pro-vision": 16384,
            "gemini-1.5-pro": 2800000,
            "gemini-1.5-flash": 1000000,
        }
        return context_limits.get(model_id, 0)
    
    def generate(self, model_id: str, messages: list[dict[str, Any]],
                **kwargs) -> dict[str, Any]:
        """Generate a completion using Gemini."""
        try:
            # Convert OpenAI-style messages to Gemini format
            gemini_messages = self._convert_messages(messages)
            
            url = f"{self.base_url}/models/{model_id}:generateContent?key={self.api_key}"
            payload = {"contents": gemini_messages}
            
            req = urllib.request.Request(url,
                                       data=json.dumps(payload).encode("utf-8"),
                                       headers={"Content-Type": "application/json"})
            
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
            
            if result and "candidates" in result and result["candidates"]:
                candidate = result["candidates"][0]
                content = candidate.get("content", {})
                text_parts = content.get("parts", [])
                text = "".join(part.get("text", "") for part in text_parts)
                
                return {
                    "ok": True,
                    "content": text,
                    "model": model_id,
                    "finish_reason": candidate.get("finishReason"),
                    "metadata": {
                        "usage": result.get("usageMetadata", {}),
                        "id": result.get("id")
                    }
                }
            return {
                "ok": False,
                "error": "invalid response from Gemini",
                "response": result
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"Gemini generation failed: {e}"
            }
    
    def stream(self, model_id: str, messages: list[dict[str, Any]],
               **kwargs):
        """Stream a completion from Gemini (generator)."""
        try:
            gemini_messages = self._convert_messages(messages)
            url = f"{self.base_url}/models/{model_id}:streamGenerateContent?key={self.api_key}"
            payload = {"contents": gemini_messages}
            
            # For streaming, we'd need to handle SSE
            # This is a simplified version
            req = urllib.request.Request(url,
                                       data=json.dumps(payload).encode("utf-8"),
                                       headers={"Content-Type": "application/json"})
            
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
            
            if result and "candidates" in result and result["candidates"]:
                candidate = result["candidates"][0]
                content = candidate.get("content", {})
                text_parts = content.get("parts", [])
                text = "".join(part.get("text", "") for part in text_parts)
                yield text
            else:
                yield ""
        except Exception as e:
            yield f"Error: {e}"
    
    def tool_call(self, model_id: str, messages: list[dict[str, Any]],
                  tools: list[dict[str, Any]], **kwargs) -> dict[str, Any]:
        """Generate a tool-calling completion using Gemini."""
        try:
            gemini_messages = self._convert_messages(messages)
            
            # Convert tools to Gemini function declaration format
            gemini_tools = self._convert_tools(tools)
            
            url = f"{self.base_url}/models/{model_id}:generateContent?key={self.api_key}"
            payload = {
                "contents": gemini_messages,
                "tools": [{"function_declarations": gemini_tools}]
            }
            
            req = urllib.request.Request(url,
                                       data=json.dumps(payload).encode("utf-8"),
                                       headers={"Content-Type": "application/json"})
            
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
            
            if result and "candidates" in result and result["candidates"]:
                candidate = result["candidates"][0]
                content = candidate.get("content", {})
                
                text_parts = []
                function_calls = []
                
                for part in content.get("parts", []):
                    if "text" in part:
                        text_parts.append(part["text"])
                    elif "functionCall" in part:
                        function_calls.append(part["functionCall"])
                
                return {
                    "ok": True,
                    "content": "".join(text_parts),
                    "tool_calls": function_calls,
                    "model": model_id,
                    "finish_reason": candidate.get("finishReason"),
                    "metadata": {
                        "usage": result.get("usageMetadata", {}),
                        "id": result.get("id")
                    }
                }
            return {
                "ok": False,
                "error": "invalid response from Gemini",
                "response": result
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"Gemini tool call failed: {e}"
            }
    
    def cancel(self, request_id: str) -> dict[str, Any]:
        """Cancel an in-progress Gemini request."""
        return {
            "ok": False,
            "error": "Gemini does not support request cancellation"
        }
    
    def health(self) -> dict[str, Any]:
        """Check Gemini health."""
        if not self.api_key:
            return {
                "provider_id": self.provider_id,
                "healthy": False,
                "status": AUTH_REQUIRED,
                "error": "API key not configured"
            }
        
        try:
            # Test with a minimal request
            url = f"{self.base_url}/models/gemini-pro:generateContent?key={self.api_key}"
            payload = {"contents": [{"parts": [{"text": "test"}]}]}
            req = urllib.request.Request(url,
                                       data=json.dumps(payload).encode("utf-8"),
                                       headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
            return {
                "provider_id": self.provider_id,
                "healthy": True,
                "status": PROVIDER_AVAILABLE
            }
        except Exception as e:
            return {
                "provider_id": self.provider_id,
                "healthy": False,
                "status": PROVIDER_UNAVAILABLE,
                "error": str(e)[:200]
            }
    
    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[dict]:
        """Convert OpenAI-style messages to Gemini format."""
        gemini_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                # Gemini doesn't have a separate system message
                # Add as user message with prefix
                gemini_messages.append({
                    "role": "user",
                    "parts": [{"text": f"System: {content}"}]
                })
            else:
                gemini_role = "user" if role == "user" else "model"
                gemini_messages.append({
                    "role": gemini_role,
                    "parts": [{"text": content}]
                })
        return gemini_messages
    
    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict]:
        """Convert OpenAI-style tools to Gemini function declarations."""
        gemini_tools = []
        for tool in tools:
            function = tool.get("function", {})
            gemini_tools.append({
                "name": function.get("name"),
                "description": function.get("description", ""),
                "parameters": function.get("parameters", {})
            })
        return gemini_tools


def create_gemini_provider_record(api_key: str = "") -> ProviderRecord:
    """Create a ProviderRecord for Gemini."""
    return ProviderRecord(
        provider_id="gemini",
        provider_family="google",
        display_name="Google Gemini",
        description="Google Gemini API for Gemini models (Gemini Pro, Gemini 1.5, etc.)",
        status=AUTH_REQUIRED if not api_key else NOT_CONFIGURED,
        authenticated=False,
        local_or_remote="remote",
        endpoint="https://generativelanguage.googleapis.com/v1beta",
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
        limitations="Requires Google Gemini API key and internet connection"
    )