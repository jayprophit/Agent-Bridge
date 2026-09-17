from model_lifecycle import ModelCapabilityProfiler

profiler = ModelCapabilityProfiler()

models = [
    'qwen2.5-coder:3b-instruct-q4_K_M',
    'qwen3.5:2b-q4_K_M', 
    'qwen3:1.7b',
    'qwen3:0.6b',
    'granite3.3:2b',
    'nomic-embed-text:latest'
]

for m in models:
    print(f'\n--- Pinging {m} ---')
    try:
        res = profiler.quick_ping(m)
        tps = res.tokens_per_sec
        ok = "YES" if res.ok else "NO"
        latency = res.first_token_s if res.first_token_s else "?"
        output = res.output[:80] if res.output else "none"
        print(f'  OK: {ok}, TPS: {tps}, First-token latency: {latency}s')
        print(f'  Output: {output}')
    except Exception as e:
        print(f'  ERROR: {e}')