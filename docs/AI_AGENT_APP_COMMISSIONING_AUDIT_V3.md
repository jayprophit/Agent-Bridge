# AI-AGENT APP COMMISSIONING AUDIT v3 — INSTALLED-ESTATE SWEEP (§7/§11)

Hermes, 2026-10-14. Owner directive: "open code also has its own list of
cloud providers free, local ones i installed for testing and more needs to be
installed and configured properly, even the local ones i installed need proper
configuration and settings. the same would go for other apps installed on the
computer that have ai agents. check in C:\Users\jpowe\Desktop\Programming
& Code and main menu options for other apps with ai agents"

Sweep of `Desktop\Programming & Code` (26 AI-relevant shortcuts) + both
Start Menu locations + running processes + installed model hosts.

## TIER 1 — ZERO-KEY CLOUD CAPACITY ALREADY INSIDE OPENCODE (the big find)

`opencode models` lists a built-in **`opencode/*` provider** — free-tier
models, NO API key, NO account:

| Model | Matches your starred list? |
|---|---|
| opencode/nemotron-3-ultra-free | ✅ (starred: nemotron-3-ultra-550b-a55b:free) |
| opencode/nemotron-3.5-lightning-free | ✅ (starred: nemotron-3.5-lightning:free) |
| opencode/space-bunny-free | ✅ (this session runs stealth/space-bunny-alpha) |
| opencode/step-5-preview-free | ✅ (starred: stepfun/step-5-preview) |
| opencode/longcat-2.5-preview-free | ~ (starred: meituan/longcat-2.Z) |
| opencode/cat-jam-free, mimo-v2.6-flash-free, muse-spark-1.3-contributor-free, big-pickle | extra free capacity |

**ACTION (in progress): repoint OpenCode's config from the 3B local Qwen to
`opencode/nemotron-3-ultra-free`** — same zero-cost posture, materially
stronger, no keys. This directly fixes the "Qwen-3B mimicked a tool call"
failure that killed M4 increment 1.

## TIER 2 — LOCAL MODEL HOSTS (installed, UNCONFIGURED into the workforce)

**Ollama** (running, :11434) — 15 models installed, only 3 wired into OpenCode:

| Installed | Wired? | Gap |
|---|---|---|
| qwen3:latest (5.2GB) | ❌ | strongest local general model — NOT in opencode config |
| phi4-mini (2.5GB) | ❌ | good small-model alternative |
| ministral-3:3b, granite4:3b, granite3.3:2b | ❌ | alternatives for routing diversity |
| deepseek-coder:1.3b, qwen2.5-coder:1.5b | ❌ | small coders |
| moondream (1.7GB, phi2+clip) | ❌ | **VISION model** — unused capability |
| nomic-embed-text | ❌ | embeddings for the knowledge layer |
| qwen2.5-coder:3b, qwen3:1.7b, qwen3.5:2b | ✅ | the 3 currently wired |

**LM Studio** (installed, ~/.lmstudio exists) — NOT running, NOT configured:
- Qwen3.5-9B-Q4_K_M.gguf (5.6GB) + mmproj (vision projector) installed
- A 9B with vision is the strongest LOCAL model available on this box —
  nothing uses it today.

**ACTIONS:** wire qwen3:latest + moondream into OpenCode's provider block;
bring LM Studio up on its own port and register it as a second local host
(LM Studio's 9B beats Ollama's 3B for real work); keep the local tier for
privacy-sensitive/offline increments only.

## TIER 3 — GUI AGENT APPS (installed, uncommissioned)

From Programming & Code + Start Menu:

| App | State | Control channel | Disposition |
|---|---|---|---|
| **Antigravity / Antigravity IDE** | RUNNING (pid 1080 earlier) | GUI agent panel — Gemini 3.8 Flash High, AX-exposed composer | AGENT_MODE_VERIFIED; task test blocked on UIA degradation; retry |
| **Claude** | shortcut present, not running | none on PATH | launch + GUI commission |
| **Cursor** | CLI is editor-launcher only | GUI composer (unprobed) | GUI probe per §15 |
| **ChatGPT** | shortcut present | web/desktop app | GUI commission (bounded task) |
| **DeepSeek / Kimi / Qwen / Manus / Devin** | shortcuts present | web/GUI | commission progressively, one at a time (resource-aware §12) |
| **OpenClaw Companion/Gateway** | installed (tray seen running) | unknown — companion+gateway suggests MCP/bridge | INVESTIGATE — possible structured channel |
| **Bionic / KRISTAL / KubeUI** | shortcuts present | unknown | identify before probing |
| **LM Studio / Ollama** | see Tier 2 | HTTP APIs | register as local model workers |

## TIER 4 — STRUCTURED-CHANNEL WORKERS (already registered)

opencode (M4 in flight), codex (entitlement, quota-limited), ollama-local.
Unchanged; the opencode provider swap (Tier 1) upgrades opencode's model.

## EXECUTION ORDER (this cycle)

1. ✅ discovery complete (this doc)
2. repoint OpenCode config → opencode/nemotron-3-ultra-free + wire
   qwen3:latest/moondream locally
3. bring LM Studio up, register as local host 2
4. re-verify OpenCode executes a REAL tool call on the new model (the 3B
   failure must not repeat) — task-specific evidence, not session age
5. progressive GUI commissioning: Antigravity retry → Claude → Cursor →
   ChatGPT, one at a time, bounded safe tasks only
6. register each verified app as a first-class WorkerRecord (§5)

Resource rule (§12): the estate is large; commission ONE heavy GUI app at a
time — the earlier CPU storm (4 duplicate API servers) proved simultaneous
launches wedge the machine.
