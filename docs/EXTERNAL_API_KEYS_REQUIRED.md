# EXTERNAL API KEYS — WHAT'S NEEDED, WHY, AND WHAT WORKS WITHOUT THEM

Hermes, 2026-10-14. Owner asked for the list so keys can be supplied manually
(this is the correct last-resort gate: I cannot and will not create/purchase
accounts; credential handling is an owner gate).

## CURRENT STATE — WHAT WORKS TODAY WITH ZERO KEYS

| Channel | Status | What it powers |
|---|---|---|
| **Ollama (local)** | ✅ LIVE (v0.40.3, :11434) | ollama-local worker; Qwen models for OpenCode; LOCAL_UNLIMITED |
| **GitHub (gh CLI)** | ✅ AUTHENTICATED (jayprophit) | git push/pull, repo estate research (§18) |
| **Codex entitlement** | ✅ auth.json present | codex-primary worker (OWNED_PAID_ENTITLEMENT — quota-limited, NOT key-based) |
| **OpenCode** | ✅ commissioned | opencode-primary worker (runs on local Ollama) |

So the programme is NOT blocked on keys — the 3-worker hive (opencode,
codex, ollama) plus gh research all work now. The keys below UNLOCK CLOUD
CAPACITY (more models, quota headroom, the hybrid-cloud lane).

## WHY THE OLD KEYS CAN'T BE REUSED

All five refs are `BLOCKED_OWNER` with reason **"credential previously
exposed"** — the previous keys leaked somewhere and MUST be rotated. That's
a security rule, not bureaucracy: reusing an exposed key is the risk itself.

## THE LIST — 5 keys, in priority order

Each becomes a KeePass entry titled exactly as shown (that's the stable ref
the whole system reads; `security/credential_broker.py` resolves by title).

| # | Get from | Signup URL | KeePass entry title | Free tier? | What it unlocks |
|---|---|---|---|---|---|
| 1 | **OpenRouter** | https://openrouter.ai/keys | `CRED-OPENROUTER-PRIMARY` | ✅ yes (free models: deepseek, llama, qwen...) | ONE key → dozens of models; the single highest-leverage key. Unified OpenAI-compatible API. |
| 2 | **Google AI Studio (Gemini)** | https://aistudio.google.com/apikey | `CRED-GEMINI-PRIMARY` | ✅ generous free tier | Gemini 2.x Flash/Pro; strong reasoning; large context. |
| 3 | **Groq** | https://console.groq.com/keys | `CRED-GROQ-PRIMARY` | ✅ free tier (fast LPU inference) | Llama/Qwen at very high speed — good for the hive scheduler's latency-sensitive calls. |
| 4 | **Hugging Face** | https://huggingface.co/settings/tokens | `CRED-HUGGINGFACE-PRIMARY` | ✅ free inference tier | Thousands of open models; also the fork/research backbone you already use. |
| 5 | **DeepSeek** | https://platform.deepseek.com/api_keys | `CRED-DEEPSEEK-PRIMARY` | ⚠️ cheap paid (NOT free) | DeepSeek V3/R1 reasoning models. **Skip if you want zero-spend** — OpenRouter serves DeepSeek free-tier anyway. |

**Recommendation: get #1 (OpenRouter) and #2 (Gemini) first.** Those two
free tiers cover the hybrid-cloud lane with materially more capacity than
the local box. #3 adds speed. #5 is optional — it costs money and
OpenRouter already routes to DeepSeek models.

## HOW TO GIVE THEM TO ME (safest path — you choose)

**Option A (recommended — I never see the raw key):**
1. Open KeePass (the broker expects `C:/Program Files/KeePass Password Safe 2/KeePass.exe`)
2. Create 5 entries in group `Aetherius`, titles EXACTLY as the table above
3. Paste each key as the entry's **password**
4. Tell me "keys are in the vault" — the runtime reads them via the broker
   (session password you unlock interactively; I never handle the master)

**Option B (one env var each, if you prefer files):**
Paste each key into `Agent-Bridge-dashboard/.env.local` (gitignored — verify
with `git check-ignore`), one per line:
```
CRED-OPENROUTER-PRIMARY=sk-or-...
CRED-GEMINI-PRIMARY=AIza...
CRED-GROQ-PRIMARY=gsk_...
CRED-HUGGINGFACE-PRIMARY=hf_...
CRED-DEEPSEEK-PRIMARY=sk-...   # optional, costs money
```
I'll wire the loader to read `.env.local` first, vault second (already the
broker's order), and the 5 adapters activate on presence — no code change
needed from you after that.

**What happens automatically once keys land** (§20 ADOPT-NOW = action):
1. `models/evidence_hybrid_cloud_reconciliation.json` flips each provider
   BLOCKED_OWNER → LIVE_VERIFIED after a real probe call
2. The hive scheduler gains cloud quota pools (FIVE_HOUR/WEEKLY/MONTHLY)
3. Model routing (§12) can pick cloud models when local is saturated —
   best permitted model per task, zero incremental spend
4. The dashboard's cloud lane shows live capacity instead of NOT_EXPOSED

## HONEST BOTTOM LINE

- **Nothing is blocked on you right now** — the 3-worker hive + gh research
  run today with zero keys.
- The keys buy **capacity and model choice**, not function.
- Never paste keys into chat — vault or .env.local only (both gitignored).
- I will not sign up for accounts or spend money; that's your gate by policy.
