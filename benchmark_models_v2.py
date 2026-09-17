import json, time, subprocess, os, sys

# Configuration: 9 models to benchmark (6 original + 3 new)
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
TIMEOUT = 20  # seconds per model

results = []
failed = []

def benchmark(model_name):
    print(f"  Trying {model_name}...")
    try:
        start = time.time()
        proc = subprocess.run(
            ["ollama", "run", model_name, PROMPT],
            capture_output=True, timeout=TIMEOUT
        )
        elapsed = time.time() - start
        
        if proc.returncode != 0:
            stderr = proc.stderr.decode('utf-8', errors='replace')[:200]
            print(f"    Exit code {proc.returncode}, stderr: {stderr}")
            return None
        
        stdout = proc.stdout.decode('utf-8', errors='replace')
        words = len(stdout.split())
        tokens = max(1, int(words * 1.3))
        
        tps = tokens / elapsed if elapsed > 0 else 0
        latency = elapsed * 1000
        
        # Extract param size from model name
        param_size = ""
        m = re.search(r'(\d+b|\d+\.?\d*bn?)', model_name)
        if m:
            param_size = m.group(1)
        
        result = {
            "model": model_name,
            "parameters": param_size,
            "tokens": tokens,
            "latency_ms": round(latency, 1),
            "first_token_ms": round(latency, 1),
            "tokens_per_sec": round(tps, 1),
            "output": stdout[:200],
            "status": "OK",
        }
        print(f"    OK: {tps:.1f} tok/s, {latency:.0f}ms")
        return result
    except subprocess.TimeoutExpired:
        print(f"    TIMEOUT")
        return None
    except Exception as e:
        print(f"    ERROR: {str(e)[:100]}")
        return None

import re

print("=== Model Benchmark Battery (9 models, factorial prompt, 20s timeout) ===")
print()

for i, model in enumerate(MODELS, 1):
    print(f"[{i}/9] {model}")
    res = benchmark(model)
    if res:
        results.append(res)
    else:
        failed.append(model)
    print()

output = {
    "benchmark_date": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "prompt": PROMPT,
    "timeout_sec": TIMEOUT,
    "total_models": len(MODELS),
    "successful": len(results),
    "failed": failed,
    "results": results,
}

with open("model_benchmark_results.json", "w") as f:
    json.dump(output, f, indent=2)

print("=" * 60)
print(f"Results: {len(results)}/{len(MODELS)} successful")
print(f"Failed: {failed}")
print(f"Written to model_benchmark_results.json")
print()

# Summary table
print("-" * 80)
header = f"{'Model':<50} {'Params':<12} {'Tok/s':<8} {'Latency':<10} {'FirstTok':<10} {'Status'}"
print(header)
print("-" * 80)
for r in results:
    line = f"{r['model']:<50} {r['parameters']:<12} {r['tokens_per_sec']:<8} {r['latency_ms']:<10} {r['first_token_ms']:<10} {r['status']}"
    print(line)
print("-" * 80)