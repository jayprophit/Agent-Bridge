import json, time, subprocess, re
from datetime import datetime

# Configuration: 9 models to benchmark (6 original + 3 new)
# 6 original: qwen2.5-coder:3b-instruct-q4_K_M, qwen3.5:2b-q4_K_M, qwen3:1.7b, qwen3:0.6b, granite3.3:2b, nomic-embed-text:latest
# 3 new: qwen2.5-coder:1.5b-instruct-q4_K_M, deepseek-coder:1.3b-instruct-q4_K_M, llama3.2:1b-instruct-q4_K_M

MODELS = [
    # Original 6
    "qwen2.5-coder:3b-instruct-q4_K_M",
    "qwen3.5:2b-q4_K_M",
    "qwen3:1.7b",
    "qwen3:0.6b",
    "granite3.3:2b",
    "nomic-embed-text:latest",
    # New 3
    "qwen2.5-coder:1.5b-instruct-q4_K_M",
    "deepseek-coder:1.3b-instruct-q4_K_M",
    "llama3.2:1b-instruct-q4_K_M",
]

PROMPT = "Write a Python function to find the factorial of a number. Return just the code."

DEFERRED = []  # Models that failed to benchmark

def benchmark_model(model_name):
    """Benchmark a single model with the test prompt."""
    print(f"  Benchmarking {model_name}...")
    try:
        start = time.time()
        result = subprocess.run(
            ["ollama", "run", model_name, PROMPT],
            capture_output=True, text=True, timeout=30
        )
        elapsed = time.time() - start
        
        if result.returncode != 0:
            print(f"    Model returned error: {result.stderr[:100]}")
            return None
        
        output = result.stdout
        # Count roughly tokens (rough: 1 token ≈ 0.75 words for English)
        words = len(output.split())
        # Rough token estimate
        tokens = max(1, int(words * 1.3))
        
        tokens_per_sec = tokens / elapsed if elapsed > 0 else 0
        latency_ms = elapsed * 1000
        
        # Estimate first token time (assume similar to full for simple prompt)
        first_token_ms = latency_ms
        
        param_size = ""
        # Try to extract parameter size from model name
        m = re.search(r'(\d+b|\d+\.?\d*bn?)', model_name)
        if m:
            param_size = m.group(1)
        
        result_data = {
            "model": model_name,
            "parameters": param_size,
            "tokens": tokens,
            "latency_ms": round(latency_ms, 1),
            "first_token_ms": round(first_token_ms, 1),
            "tokens_per_sec": round(tokens_per_sec, 1),
            "output_preview": output[:100] + ("..." if len(output) > 100 else ""),
            "status": "OK",
        }
        print(f"    OK: {tokens_per_sec:.1f} tok/s, {latency_ms:.0f}ms latency")
        return result_data
    except subprocess.TimeoutExpired:
        print(f"    TIMEOUT after 30s")
        return None
    except Exception as e:
        print(f"    ERROR: {str(e)[:100]}")
        return None

print(f"=== Model Benchmark Battery ===")
print(f"Prompt: {PROMPT}")
print(f"Models: {len(MODELS)}")
print(f"Started at: {datetime.now().isoformat()}")
print()

all_results = []
for i, model in enumerate(MODELS, 1):
    print(f"[{i}/{len(MODELS)}] {model}")
    res = benchmark_model(model)
    if res:
        all_results.append(res)
    else:
        Deferred.append(model)
    print()

# Write results
output = {
    "benchmark_date": datetime.now().isoformat(),
    "prompt": PROMPT,
    "models_tested": len(all_results),
    "deferred": Deferred,
    "results": all_results,
}

with open("model_benchmark_results.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"=== Benchmark Complete ===")
print(f"Successful: {len(all_results)}/{len(MODELS)}")
print(f"Deferred: {Deferred}")
print(f"Results written to model_benchmark_results.json")
print()

# Print summary table
print("-" * 80)
print(f"{'Model':<50} {'Params':<12} {'Tok/s':<8} {'Latency':<10} {'FirstTok':<10} {'Status'}")
print("-" * 80)
for r in all_results:
    print(f"{r['model']:<50} {r['parameters']:<12} {r['tokens_per_sec']:<8} {r['latency_ms']:<10} {r['first_token_ms']:<10} {r['status']}")
print("-" * 80)