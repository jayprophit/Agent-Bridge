# v0.8 Resource Balance Report (Part A + convergence real workload)

Model: qwen3:0.6b (local Ollama, disposable fixtures; MAT untouched)

BASELINE (sequential): 2.824s
ADAPTIVE (waves+placement): 2.334s
Waves: 2, queue depth: 2
Inference TTFT: 1.789s, tokens/sec: 22.36
Files: 20 (19370 bytes), tests ok: True
Headroom: OK, status: PASS

Prior synthetic figure preserved for comparison: 0.396s -> 0.096s (12 synthetic tasks, no backend).

Backend controls: Ollama num_predict/temperature applied; tensor placement, VRAM control and NPU are BACKEND_CONTROL_UNAVAILABLE.
