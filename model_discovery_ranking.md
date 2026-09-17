# Local Model Discovery & Ranking for i7-870 + 16GB + GTX 1050 Ti

## Hardware Constraints
- CPU: Intel Core i7-870 (4 cores, 8 threads, ~2.93GHz base)
- RAM: ~16GB system RAM
- GPU: NVIDIA GeForce GTX 1050 Ti (4GB VRAM, but laptop variant may share bandwidth)
- OS: Windows 10 Pro
- Ollama installed with 8 models currently

## Currently Installed Models (8 total)
1. nomic-embed-text:latest - embedding only, ~176M params - CPU friendly
2. granite3.3:2b - 2.8B params, IBM research, reasoning focus
3. hhao/qwen2.5-coder-tools:3b - 3B params, Qwen coding family
4. qwen2.5-coder:3b-instruct-q4_K_M - 3B params, Qwen2.5 coding instruct
5. qwen3.5:2b-q4_K_M - 2B params, Qwen3.5 quantized
6. qwen3:latest - Qwen3 family, various sizes
7. qwen3:1.7b - 1.7B params, Qwen3 small
8. qwen3:0.6b - 0.6B params, Qwen3 tiny

## Downloadable Candidates (Ranked by Hardware Fit)

### Tier 1: Strong candidates - 1.5B-3B quantized Qwen/Qwen2.5/Coder families

1. **qwen2.5-coder:1.5b-instruct-q4_K_M** 
   - 1.5B parameters, Q4_K_M quantization (~3GB RAM)
   - Excellent coding capability, efficient CPU inference
   - Same family as installed qwen2.5-coder:3b, smaller/faster
   - Estimated: 8-12 tokens/sec on i7-870 CPU

2. **deepseek-coder:1.3b-instruct-q4_K_M**
   - 1.3B parameters, Q4_K_M quantization (~2.6GB RAM)
   - Strong coding performance, good instruction following
   - Well-optimized for consumer hardware
   - Estimated: 10-15 tokens/sec on i7-870 CPU

3. **phi-3-mini:3.8b-instruct-q4_K_M**
   - 3.8B parameters, Q4_K_M quantization (~4GB RAM - at limit)
   - Microsoft model, surprising capability for size
   - Good reasoning + coding balance
   - Estimated: 5-8 tokens/sec on i7-870 CPU

### Tier 2: Viable candidates - 7B quantized (may be tight)

4. **llama3.2:1b-instruct-q4_K_M**
   - 1B parameters, very lightweight
   - Fastest inference, good for simple tasks
   - Limited reasoning compared to larger models
   - Estimated: 20-30 tokens/sec on i7-870 CPU

5. **mixtral:8x7b-instruct-q4_0** 
   - 8x7B mixture but only 2.8B active per token
   - Good reasoning, moderate coding
   - May be tight on 16GB RAM (needs ~8-10GB)
   - Estimated: 3-5 tokens/sec on i7-870 CPU

6. **starcoder2:1.5b**
   - 1.5B params, code-focused
   - Good for code completion tasks
   - Similar performance to qwen2.5-coder 1.5B
   - Estimated: 8-12 tokens/sec on i7-870 CPU

### Tier 3: Lower priority - too large or niche

7. **llama3.1:8b-instruct-q4_K_M** - may struggle on 16GB CPU-only
8. **gemma2:9b-instruct-q4_K** - VRAM/RAM pressure
9. **qwen2:7b-instruct-q4_K_M** - borderline on 16GB

## Recommended Download Priority (Max 3)

### TOP 3 RECOMMENDATIONS

1. **qwen2.5-coder:1.5b-instruct-q4_K_M** 
   - Best overall fit: coding + efficiency + same family
   - Will complement existing 3B version with a faster alternative
   - Estimated RAM: ~3GB (Q4_K_M)
   - Estimated CPU throughput: 8-12 tokens/sec

2. **deepseek-coder:1.3b-instruct-q4_K_M**
   - Strong coder, different family for model diversity
   - Good instruction following
   - Estimated RAM: ~2.6GB (Q4_K_M)
   - Estimated CPU throughput: 10-15 tokens/sec

3. **phi-3-mini:3.8b-instruct-q4_K_M**
   - Microsoft model, different architecture family
   - Strong reasoning surprising for 3.8B size
   - Estimated RAM: ~4GB (at upper limit, Q4_K_M)
   - Estimated CPU throughput: 5-8 tokens/sec

## Expected Model Pool After Download (9 total)

| Role | Model | Size | Q Quant | Key Strength |
|------|-------|------|---------|-------------|
| PRIMARY_CODER | qwen2.5-coder:3b-instruct-q4_K_M | 3B | Q4_K_M | Strong coding |
| FAST_CODER | qwen2.5-coder:1.5b-instruct-q4_K_M | 1.5B | Q4_K_M | Fast coding |
| GENERAL_REASONER | phi-3-mini:3.8b-instruct-q4_K_M | 3.8B | Q4_K_M | Reasoning |
| REVIEWER_DEBUGGER | deepseek-coder:1.3b-instruct-q4_K_M | 1.3B | Q4_K_M | Code review |
| EMBEDDING | nomic-embed-text:latest | ~176M | N/A | Embeddings |
| FALLBACK | qwen3:0.6b | 0.6B | Q4_K_M | Light duty |
| PLACEHOLDER | granite3.3:2b | 2.8B | Q4_K_M | IBM reasoning |
| NEW_CODER | deepseek-coder:1.3b-instruct-q4_K_M | 1.3B | Q4_K_M | Code focus |
| NEW_REASONER | phi-3-mini:3.8b-instruct-q4_K_M | 3.8B | Q4_K_M | Reasoning focus |

## Retirement Plan for Obsolete Models

Under MODEL_DELETION_APPROVED=CONDITIONAL gate:
- Remove models not matching final role assignment
- qwen3:1.7b and qwen3:0.6b may be retired if phi-3 and deepseek fill roles
- hhao/qwen2.5-coder-tools:3b - redundant with qwen2.5-coder family
- Decision: keep top 3 by benchmark, retire rest under conditional gate

## Benchmark Battery (Same Controlled Task)

All models benchmarked on same tasks:
- Coding: Fibonacci, prime sieve, JSON parsing
- Reasoning: Raven matrices, logic puzzles  
- Extraction: Named entity, summary generation
- Metrics: tokens/sec, latency_ms, first_token_ms, accuracy