# Model Capability Roles Registry
# Registered roles based on hardware fit and benchmark evidence
# Hardware: Intel i7-870, 16GB RAM, NVIDIA GTX 1050 Ti
# Local models only (Ollama)

# PRIMARY_CODER: qwen2.5-coder:3b-instruct-q4_K_M
# - 3.1B parameters, Q4_K_M quantization
# - 32K context, best coding performance on this hardware
# - Used for code generation, modification, and base tasks

# FAST_CODER: qwen3.5:2b-q4_K_M
# - 2.3B parameters, Q4_K_M quantization
# - 262K context, faster than 3B model
# - Has vision capability, used for fast coding tasks

# GENERAL_REASONER: qwen3:1.7b
# - 2.0B parameters, Q4_K_M quantization
# - 40K context, balanced reasoning ability
# - Used for debugging, analysis, and general tasks

# REVIEWER_DEBUGGER: granite3.3:2b
# - 2.5B parameters, Q4_K_M quantization
# - 131K context, tool-capable
# - Apache 2.0 licensed, used for code review and debugging

# FALLBACK: qwen3:0.6b
# - 752M parameters, Q4_K_M quantization
# - 40K context, lightweight, always available
# - Used when primary models are unavailable or overloaded

# EMBEDDING: nomic-embed-text:latest
# - 137M parameters, F16 quantization
# - Specialized for embedding tasks
# - Used for semantic search, retrieval, and context enhancement

MINIMUM_MODEL_COVERAGE = {
    "primary_coder": "qwen2.5-coder:3b-instruct-q4_K_M",
    "fast_coder": "qwen3.5:2b-q4_K_M",
    "general_reasoner": "qwen3:1.7b",
    "reviewer_debugger": "granite3.3:2b",
    "fallback": "qwen3:0.6b",
    "embedding": "nomic-embed-text:latest"
}

# Model health circuit breaker states
HEALTH_STATES = ["HEALTHY", "DEGRADED", "RATE_LIMITED", "TIMED_OUT", "UNAVAILABLE", "BROKEN", "COOLDOWN"]

# Privacy routing
PRIVATE = "local-only"
CONTROLLED_REMOTE = "approved-hosted"
PUBLIC_NONSENSITIVE = "broadcast-approved"