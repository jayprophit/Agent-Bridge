import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from model_lifecycle import ModelRegistry, ModelLifecycleManager, ModelRecord, ModelStatus, SizeClass, CapabilityProfile

# Register the 9 models from the classical pool
reg = ModelRegistry()

CLASSICAL_MODEL_POOL = {
    "PRIMARY_CODER": "qwen2.5-coder:3b-instruct-q4_K_M",
    "FAST_CODER": "qwen2.5-coder:1.5b-instruct-q4_K_M",
    "GENERAL_REASONER": "granite3.3:2b",
    "REVIEWER_DEBUGGER": "deepseek-coder:1.3b-instruct-q4_K_M",
    "EMBEDDING": "nomic-embed-text:latest",
    "FALLBACK": "qwen3:0.6b",
    "SECONDARY_GENERAL": "qwen3.5:2b-q4_K_M",
    "BACKUP_FAST": "llama3.2:1b-instruct-q4_K_M",
    "TERTIARY_REASONER": "qwen3:1.7b",
}

# Parameter sizes mapping
PARAM_SIZES = {
    "qwen2.5-coder:3b-instruct-q4_K_M": 3.0,
    "qwen2.5-coder:1.5b-instruct-q4_K_M": 1.5,
    "granite3.3:2b": 2.8,
    "deepseek-coder:1.3b-instruct-q4_K_M": 1.3,
    "nomic-embed-text:latest": 0.176,
    "qwen3.5:2b-q4_K_M": 2.0,
    "llama3.2:1b-instruct-q4_K_M": 1.0,
    "qwen3:1.7b": 1.7,
    "qwen3:0.6b": 0.6,
}

for role, model_id in CLASSICAL_MODEL_POOL.items():
    params = PARAM_SIZES[model_id]
    rec = ModelRecord(
        model_id=model_id, provider="ollama", family=model_id.split(":")[0],
        parameters_b=params, status=ModelStatus.EXPERIMENTAL
    )
    # Set capabilities based on role
    if role == "EMBEDDING":
        rec.capabilities.scores = {"coding": False, "reasoning": False, "embedding": True}
    else:
        rec.capabilities.scores = {"coding": True, "reasoning": True, "embedding": False}
    reg.register(rec)

print("Registry has", len(reg.models), "models")
print()

# Test default_set
picks = ModelLifecycleManager.default_set(reg)
print("default_set picks:", picks)
print()

# Test retirement plan
retirement_plan = ModelLifecycleManager.retirement_plan(reg)
print("retirement_plan:", retirement_plan)
print()

# Test placement
from model_lifecycle import ModelPlacementEngine
engine = ModelPlacementEngine()
device = {"ram_free_gb": 16.0, "gpu": False, "remote_available": False}

print("Model placements:")
for role, model_id in CLASSICAL_MODEL_POOL.items():
    rec = reg.get(model_id)
    if rec:
        score, reasons = engine.score(rec, {"capabilities": ["coding"]}, device)
        placement = engine.place(rec, {"capabilities": ["coding"]}, device)
        print(f"  {role} ({model_id}): score={score}, placement={placement}")