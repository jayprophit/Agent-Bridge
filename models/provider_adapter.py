"""ProviderAdapter interface (v0.7). Generic provider contract.

All model providers (Ollama, OpenAI, Anthropic, etc.) implement this interface.
The runtime never calls provider-specific methods directly — it uses this
generic contract, enabling hot-swappable providers.
"""
from __future__ import annotations

from typing import Any


class ProviderAdapter:
    """Generic provider interface. All providers implement this shape."""
    
    provider_id: str = ""
    provider_family: str = ""
    
    # -- discovery ---------------------------------------------------------
    def discover(self) -> dict[str, Any]:
        """Discover available models from this provider.
        
        Returns:
            Dict with 'models' list and provider metadata.
        """
        return {"provider_id": self.provider_id, "models": []}
    
    def authenticate(self, credentials: dict[str, Any] | None = None) -> dict[str, Any]:
        """Authenticate with the provider if needed.
        
        Args:
            credentials: Optional auth credentials (API keys, etc.)
            
        Returns:
            Dict with 'authenticated' bool and any auth metadata.
        """
        return {"provider_id": self.provider_id, "authenticated": False,
                "reason": "not implemented"}
    
    # -- model information ---------------------------------------------------
    def list_models(self) -> list[dict[str, Any]]:
        """List all available models from this provider.
        
        Returns:
            List of model metadata dicts.
        """
        return []
    
    def model_info(self, model_id: str) -> dict[str, Any]:
        """Get detailed information about a specific model.
        
        Args:
            model_id: The model identifier.
            
        Returns:
            Dict with model capabilities and metadata.
        """
        return {"model_id": model_id, "available": False,
                "error": "model not found"}
    
    def capabilities(self) -> dict[str, Any]:
        """Report provider-level capabilities.
        
        Returns:
            Dict with provider capabilities (streaming, tool_calling, etc.).
        """
        return {"provider_id": self.provider_id, "capabilities": {}}
    
    # -- inference -----------------------------------------------------------
    def context_limit(self, model_id: str) -> int:
        """Get context window size for a model.
        
        Args:
            model_id: The model identifier.
            
        Returns:
            Context token limit (0 if unknown).
        """
        return 0
    
    def generate(self, model_id: str, messages: list[dict[str, Any]],
                **kwargs) -> dict[str, Any]:
        """Generate a completion.
        
        Args:
            model_id: The model to use.
            messages: Chat messages in standard format.
            **kwargs: Additional generation parameters.
            
        Returns:
            Dict with 'ok' bool, 'content', and metadata.
        """
        raise NotImplementedError
    
    def stream(self, model_id: str, messages: list[dict[str, Any]],
               **kwargs):
        """Stream a completion (generator).
        
        Args:
            model_id: The model to use.
            messages: Chat messages in standard format.
            **kwargs: Additional generation parameters.
            
        Yields:
            Chunks of the generated response.
        """
        raise NotImplementedError
    
    def tool_call(self, model_id: str, messages: list[dict[str, Any]],
                  tools: list[dict[str, Any]], **kwargs) -> dict[str, Any]:
        """Generate a tool-calling completion.
        
        Args:
            model_id: The model to use.
            messages: Chat messages.
            tools: Available tool definitions.
            **kwargs: Additional parameters.
            
        Returns:
            Dict with tool call results.
        """
        raise NotImplementedError
    
    # -- control ------------------------------------------------------------
    def cancel(self, request_id: str) -> dict[str, Any]:
        """Cancel an in-progress request.
        
        Args:
            request_id: The request to cancel.
            
        Returns:
            Dict with cancellation status.
        """
        return {"ok": False, "error": "cancel not supported"}
    
    def health(self) -> dict[str, Any]:
        """Check provider health.
        
        Returns:
            Dict with 'healthy' bool and health details.
        """
        return {"provider_id": self.provider_id, "healthy": False,
                "status": "unknown"}