# MODEL ROUTING POLICY — STARRED FREE MODELS FIRST (owner directive 2026-10-14)

Owner: "i have starred free models in hermes use these instead of models that
need api keys as they will need a paid tier usually" + "also check the list
for none starred models that may work that dont need api keys".

This replaces the "get 5 API keys" framing in EXTERNAL_API_KEYS_REQUIRED.md.
Keys are now LAST RESORT, not first. The starred free models are the
primary workforce routing.

## STARRED MODELS (extracted from the desktop picker's `favorite-models` key)

Source: `AppData/Roaming/Hermes/Local Storage/leveldb/004534.ldb`, key
`favorite-models`. Verified against the live OpenRouter catalog:

| Starred model | Context | Free tier | Notes |
|---|---|---|---|
| openrouter::thinkingmachines/inkling-small:free | 1024k | ✅ FREE | strongest free pick — 1M context |
| nvidia/nemotron-3.5-lightning:free | 976k | ✅ FREE | fast, huge context |
| nvidia/nemotron-3-ultra-550b-a55b:free | 976k | ✅ FREE | 550B MoE, strongest reasoning |
| nvidia/nemotron-3-super-120b-a12b:free | 256k | ✅ FREE | mid-weight, fast |
| nous::upstage/solar-mini4:free | — | ✅ FREE (Nous inference) | runs on THIS session's provider |
| stepfun/step-5-preview | 976k | ⚠️ paid on OpenRouter | **but** `stealth/space-bunny-alpha` (the session model, Nous) is the free equivalent in use |
| meituan/longcat-2.Z, inclusionai/ling-3.0-flash-sante6, poolside/laguna-xs-2.1v | — | Nous-provider free variants | resolve via the `nous::` prefix (this session's provider) |

**Key insight:** the `nous::` prefix = the Nous inference API — the SAME
provider this Hermes session already runs on (`stealth/space-bunny-alpha`,
free). So 4 of the 9 starred models route through a provider that ALREADY
works with zero new keys.

## NON-STARRED FREE MODELS WORTH KNOWING (no keys needed)

Verified free on OpenRouter (`prompt` price == 0), coding-capable, NOT yet
starred — candidates for the hive when the starred set is busy:

- `google/gemma-4-31b-it:free` (256k) — Google's open Gemma
- `google/gemma-4-26b-a4b-it:free` (256k)
- `cohere/north-mini-code:free` (250k) — code-specialised
- `inclusionai/ling-3.1-flash` (262k)
- `apodex/apodex-1.1-mini:free`, `dots-studio/dots-3-note-preview:free` (512k),
  `liquid/lfm-2.5-2.6b:free` — smaller/faster, good for bounded increments

Plus the zero-key local tier that never changes: **Ollama** (local,
LOCAL_UNLIMITED — Qwen 2.5 Coder 3B currently pins OpenCode).

## ROUTING POLICY (hard-coded preference order)

For every AI assignment (§12 model routing):

1. **Starred free models** (this session's Nous provider first — zero keys,
   zero marginal cost, already authenticated)
2. **Non-starred free models** (OpenRouter `:free` tier — still zero keys
   via the existing Hermes credential, NOT a new API key)
3. **Local Ollama** (free, unlimited, but weak — 3B; only for bounded
   increments or when cloud is rate-limited)
4. **Codex entitlement** (owned, quota-limited — its own auth.json, no key)
5. **API-key providers LAST RESORT** — only if the owner explicitly supplies
   a key in `.env.local` or KeePass (see EXTERNAL_API_KEYS_REQUIRED.md)

Owner's reasoning, adopted as policy: keyed providers "will need a paid tier
usually" — so the DEFAULT is free-tier-only routing, and a key is never
required for the programme to run (§35: block only the action that needs it).

## WHAT THIS MEANS FOR THE WORKFORCE

- OpenCode can be pointed at `nous::` starred models instead of the 3B local
  Qwen for M4 increments (stronger, still free, no keys)
- The hive scheduler's cloud lane uses the `:free` OpenRouter models through
  the EXISTING Hermes credential — no CRED-* rotation needed
- The 5 BLOCKED_OWNER refs stay dormant; they unlock EXTRA capacity only if
  the owner later chooses to supply keys
- `compute/credential_loader.py` stays as the activation path — keys land →
  providers go live, automatically, whenever the owner wants
