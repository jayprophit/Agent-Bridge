# Resource Orchestration (v0.8, Part A)

Capability pool built from profiler output (`resources/pool.py`), rule-based
workload classification (`classifier.py`), dependency-aware scheduling
(`scheduler.py`), evidence-weighted placement (`balancer.py`), live pressure
(`monitor.py`). Reuses DeviceProfiler/HardwareProfiler/RuntimeTuner/
BenchmarkHistory; probes nothing itself.

Ollama offload controls (`num_gpu`, `num_thread`) are declared-partial
(documented, not benchmark-verified); anything else records
`BACKEND_CONTROL_UNAVAILABLE`. Lane reserves keep INTERACTIVE machines
usable (see ADAPTIVE_BALANCING.md, WORKLOAD_PLACEMENT.md).
