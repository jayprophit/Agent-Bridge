"""Local-model example (needs Ollama + a qwen3 model): think control.

Reasoning models must answer in `content` for tool use. Pass think=False
explicitly; the adapter never sends the flag unprompted.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from models.providers.ollama_provider import OllamaProvider

p = OllamaProvider()
print("capabilities:", p.capabilities().get("supports_think_control"))
out = p.generate("qwen3:1.7b",
                 [{"role": "user", "content": "Reply with exactly: OK"}],
                 think=False)
print("content:", repr(out.get("content", "")[:80]))
print("thinking_chars:", out["metadata"]["thinking_chars"])
