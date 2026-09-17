# Hosted Model Catalogue - OpenCode Classification

## Classification Schema

Each model is classified into one of these categories:

- **LOCAL_INSTALLED** - Model already installed locally via Ollama
- **LOCAL_DOWNLOADABLE** - Model available for download via Ollama, compatible with hardware
- **HOSTED_FREE** - Free hosted API endpoint (no cost, rate-limited or generous tier)
- **HOSTED_PAID** - Paid hosted API required
- **API_ONLY** - Model accessible only via API, not downloadable locally
- **UNAVAILABLE** - Model not accessible, archived, or discontinued
- **UNKNOWN** - Classification not yet determined

## LOCAL_INSTALLED (already via Ollama)

| Model | Size | Family | Quantisation | VRAM/RAM Estimate | Capabilities |
|-------|------|--------|-------------|-------------------|-------------|
| nomic-embed-text:latest | ~176M | embedding | N/A | ~512MB RAM | embedding |
| granite3.3:2b | 2.8B | IBM research | Q4_K_M | ~2.4GB RAM | reasoning, general chat |
| hhao/qwen2.5-coder-tools:3b | 3B | Qwen coding tools | Unknown | ~3GB RAM | coding tools |
| qwen2.5-coder:3b-instruct-q4_K_M | 3B | Qwen2.5 coding | Q4_K_M | ~3GB RAM | coding, instruction following |
| qwen3.5:2b-q4_K_M | 2B | Qwen3.5 | Q4_K_M | ~2GB RAM | reasoning, coding |
| qwen3:1.7b | 1.7B | Qwen3 | Q4_K_M | ~1.5GB RAM | general chat, reasoning |
| qwen3:0.6b | 0.6B | Qwen3 | Q4_K_M | ~1GB RAM | light duty, testing |
| qwen2.5-coder:1.5b-instruct-q4_K_M | 1.5B | Qwen2.5 coding | Q4_K_M | ~2GB RAM | fast coding |
| deepseek-coder:1.3b-instruct-q4_K_M | 1.3B | DeepSeek coding | Q4_K_M | ~2GB RAM | coding, instruction following |
| llama3.2:1b-instruct-q4_K_M | 1B | Llama3.2 | Q4_K_M | ~1.5GB RAM | general purpose, fast |

## LOCAL_DOWNLOADABLE (available, compatible with i7-870 + 16GB + GTX 1050 Ti)

| Model | Size | Family | Quantisation | Est. RAM | Why Downloaded |
|-------|------|--------|-------------|----------|----------------|
| phi-3-mini:3.8b-instruct-q4_K_M (attempted) | 3.8B | Microsoft | Q4_K_M | ~4GB | Strong reasoning for size (but file not found) |
| Other 7B+ quantized | 7B+ | Various | Q4_K_M | >8GB | Too large for 16GB RAM CPU-only |

## HOSTED_FREE (free API endpoints available)

| Service | Model(s) | Cost | Rate Limits | Notes |
|---------|----------|------|-------------|-------|
| OpenAI | gpt-3.5-turbo, gpt-4o | Paid | Varies | Not free beyond trial |
| Anthropic | claude-3-haiku, claude-3-sonnet | Paid | Varies | Not free |
| Google Gemini | gemini-1.5-flash, gemini-1.5-pro | Paid | Varies | Not free |
| Ollama hosted instances | Various local models | Free (self-hosted) | Self-determined | This catalogue's focus |
| Hugging Face Inference API | Various open models | Free tier | 30 RPM approx | Some models free with account |
| Together AI | Mixtral, Llama 3 | Free tier | Varies | Free tier available |
| DeepInfra | Various models | Paid | Varies | Not free |

## HOSTED_PAID (requires payment for API access)

| Service | Model(s) | Cost Structure |
|---------|----------|----------------|
| OpenAI | gpt-4o, gpt-4o-mini, gpt-3.5-turbo | Pay-per-token |
| Anthropic | claude-3.5-sonnet, claude-3-haiku | Pay-per-token |
| Google Gemini | gemini-1.5-pro, gemini-1.5-flash | Pay-per-token |
| Cohere | Various | Pay-per-token |
| AWS Bedrock | Titan, Claude, Llama | Pay-per-token |
| Azure OpenAI | GPT-4, GPT-3.5 | Pay-per-token + reservation |

## API_ONLY (accessible via API, not downloadable locally)

| Model | Provider | Access Method |
|-------|----------|----------------|
| gpt-4o | OpenAI | API key |
| claude-3-5-sonnet | Anthropic | API key |
| gemini-1.5-pro | Google | API key |
| codex-openai | OpenAI | API key |

## UNAVAILABLE / Discontinued

| Model | Reason |
|-------|--------|
| codex (original) | Discontinued, replaced by codex-openai |
| gpt-3 | Legacy, superseded |
| LLaMA 1.0 | Superseded by LLaMA 2/3 |

## UNKNOWN (not yet checked)

Models not yet classified through the intake process.

---

## Model Pool Classification Summary

| Classification | Count | Models |
|---------------|-------|--------|
| LOCAL_INSTALLED | 10 | nomic-embed-text, granite3.3, qwen2.5-coder:3b, qwen3.5:2b-q4_K_M, qwen3:1.7b, qwen3:0.6b, qwen2.5-coder:1.5b-instruct-q4_K_M, deepseek-coder:1.3b-instruct-q4_K_M, llama3.2:1b-instruct-q4_K_M |
| LOCAL_DOWNLOADABLE | 0 | None currently viable for this hardware at 7B+ |
| HOSTED_FREE | 0 | None classified yet (would require API keys) |
| HOSTED_PAID | 0 | None classified |
| API_ONLY | 0 | None classified |
| UNAVAILABLE | 3 | codex (original), gpt-3, LLaMA 1.0 |
| UNKNOWN | Pending | Any model not yet inspected |

---

## Recommended Next Steps for Catalogue

1. **Classify hosted API resources** - Test Hugging Face Inference API with free account
2. **Update model roles** - Ensure LOCAL_INSTALLED models align with CLASSICAL_MODEL_POOL assignments
3. **Add API gateway integration** - Connect Agent Bridge ModelRouter to hosted providers where beneficial
4. **Document API cost estimates** - For categories where paid hosting is evaluated
5. **Create API-on-demand fallback** - Route through hosted providers when local models fail gate checks