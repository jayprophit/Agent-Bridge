"""Safe local AI runtime discovery using configured endpoints and PATH."""
from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class RuntimeDescriptor:
    runtime_id: str
    name: str
    status: str = "UNAVAILABLE"
    executable: str = ""
    endpoint: str = ""
    protocol: str = "UNKNOWN"
    version: str = ""
    models: list[dict[str, Any]] = field(default_factory=list)
    discovery_source: str = ""
    limitations: list[str] = field(default_factory=list)


class LocalRuntimeDiscovery:
    """Discover only registered/configured local endpoints; never scans ports.

    Uses a protocol probe chain for configured candidates:
    OLLAMA_COMPATIBLE -> OPENAI_COMPATIBLE -> AGENT_BRIDGE_NATIVE -> UNKNOWN

    Only probes safe documented/configured URLs. No arbitrary port scanning.
    """

    def __init__(self, endpoints: dict[str, str] | None = None,
                 timeout_seconds: float = 1.5) -> None:
        self.endpoints = endpoints or {
            "ollama": "http://127.0.0.1:11434",
        }
        self.timeout_seconds = timeout_seconds
        self._last: dict[str, RuntimeDescriptor] = {}

    def discover(self) -> list[RuntimeDescriptor]:
        found: dict[str, RuntimeDescriptor] = {}
        for runtime_id, endpoint in self.endpoints.items():
            # Start with previous descriptor if available to retain metadata
            previous = self._last.get(runtime_id)
            descriptor = RuntimeDescriptor(
                runtime_id=runtime_id, name=runtime_id,
                endpoint=endpoint, discovery_source="configured_endpoint",
            )
            executable = shutil.which(runtime_id)
            if executable:
                descriptor.executable = executable
                descriptor.discovery_source = "path_and_configured_endpoint"
                descriptor.version = self._version(executable)

            # Retain metadata from previous discovery
            if previous:
                descriptor.models = previous.models
                descriptor.version = descriptor.version or previous.version
                descriptor.executable = descriptor.executable or previous.executable
                descriptor.discovery_source = "refresh"

            # Protocol probe chain - try each protocol in order
            probe_chain = [
                ("OLLAMA_COMPATIBLE", self._probe_ollama),
                ("OPENAI_COMPATIBLE", self._probe_openai_compatible),
                ("AGENT_BRIDGE_NATIVE", self._probe_agent_bridge_native),
            ]

            probe_succeeded = False
            for protocol_name, probe_fn in probe_chain:
                try:
                    probe_fn(descriptor)
                    if descriptor.status == "HEALTHY":
                        descriptor.protocol = protocol_name
                        probe_succeeded = True
                        break
                except Exception as exc:
                    descriptor.limitations.append(f"{protocol_name}: {type(exc).__name__}")

            # If no protocol succeeded, determine status based on history
            if not probe_succeeded:
                descriptor.protocol = "UNKNOWN"
                if previous and previous.status == "HEALTHY":
                    # Previously healthy, now unreachable -> OFFLINE with retained metadata
                    descriptor.status = "OFFLINE"
                elif descriptor.limitations:
                    # Never successfully probed, has probe errors -> ADAPTER_REQUIRED
                    descriptor.status = "ADAPTER_REQUIRED"
                else:
                    # No info at all -> UNAVAILABLE
                    descriptor.status = "UNAVAILABLE"

            found[runtime_id] = descriptor

        # Retain offline metadata for previously seen runtimes no longer in config
        for runtime_id, previous in self._last.items():
            if runtime_id not in found:
                previous.status = "OFFLINE"
                found[runtime_id] = previous

        self._last = found
        return sorted(found.values(), key=lambda item: item.runtime_id)

    def _request_json(self, url: str) -> Any:
        with urllib.request.urlopen(url, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def _probe_ollama(self, descriptor: RuntimeDescriptor) -> None:
        """Probe Ollama-compatible /api/tags endpoint."""
        data = self._request_json(descriptor.endpoint.rstrip("/") + "/api/tags")
        models = data.get("models", []) if isinstance(data, dict) else []
        descriptor.models = [
            {key: model[key] for key in ("name", "size", "details", "capabilities")
             if key in model}
            for model in models if isinstance(model, dict)
        ]
        descriptor.status = "HEALTHY"

    def _probe_openai_compatible(self, descriptor: RuntimeDescriptor) -> None:
        """Probe OpenAI-compatible /v1/models endpoint."""
        data = self._request_json(descriptor.endpoint.rstrip("/") + "/v1/models")
        descriptor.models = data.get("data", []) if isinstance(data, dict) else []
        descriptor.status = "HEALTHY"

    def _probe_agent_bridge_native(self, descriptor: RuntimeDescriptor) -> None:
        """Probe Agent Bridge native protocol endpoint."""
        # Try a native health endpoint
        data = self._request_json(descriptor.endpoint.rstrip("/") + "/health")
        if isinstance(data, dict) and data.get("status") == "ok":
            descriptor.models = data.get("models", [])
            descriptor.status = "HEALTHY"
        else:
            raise ValueError("Not an Agent Bridge native endpoint")

    @staticmethod
    def _version(executable: str) -> str:
        try:
            result = subprocess.run(
                [executable, "--version"], capture_output=True, text=True,
                timeout=2, check=False,
            )
            return (result.stdout or result.stderr).strip()[:200]
        except (OSError, subprocess.SubprocessError):
            return ""
