# EXTERNAL WORKER COMMISSIONING AUDIT (§10/§20)
Hermes, 2026-10-13. DISCOVER → LAUNCH → IDENTIFY → PLAN/TIER → MODEL → QUOTA
→ CONTROL TEST → TASK TEST → RESULT TEST → HANDOFF TEST → REGISTER.

## CONTROL-CHANNEL PRIORITY (owner law): native API > MCP/A2A > CLI > scripting
> plugin > file > accessibility > browser > mouse/keyboard. GUI automation is
LAST resort, only when no structured channel exists.

## AUDIT RESULTS
| app | state | control channel | disposition | reason |
|---|---|---|---|---|
| opencode | RUNNING, commissioned | CLI (`opencode run`) | **REGISTERED** (opencode-primary) | headless delivery verified LIVE_VERIFIED |
| codex | RUNNING, commissioned | CLI (`codex exec resume`) | **REGISTERED** (codex-primary) | quota restored 06:16, on MAT |
| ollama | RUNNING, commissioned | HTTP `/api/generate` | **REGISTERED** (ollama-local) | local free tier |
| claude | RUNNING (pid 8696) | none on PATH | DEFERRED_NO_CHANNEL | GUI app; no CLI/API/MCP discovered; needs bridge |
| manus | RUNNING (pid 12604) | none on PATH | DEFERRED_NO_CHANNEL | GUI app; no structured channel |
| cursor | CLI present | `cursor.cmd` = editor launcher only | DEFERRED_NO_AGENT_MODE | no `cursor-agent`; `--version` empty; not an agent CLI |
| antigravity | Start-menu shortcut | not probed | PENDING_PROBE | GUI; needs launch+inspect |
| deepseek | Start-menu shortcut | not probed | PENDING_PROBE | GUI/web |
| devin | Start-menu shortcut | not probed | PENDING_PROBE | web agent |
| kimi | Start-menu shortcut | not probed | PENDING_PROBE | GUI/web |
| qwen | Start-menu shortcut | not probed | PENDING_PROBE | GUI; may share Ollama local pool |
| openclaw | shortcuts present | not probed | PENDING_PROBE | companion+gateway; possible MCP bridge |

## RULE (§20): a failed/unavailable candidate records its EXACT reason and the
audit CONTINUES to the next. Commissioning does not block on one app. The 3
registered workers (opencode/codex/ollama) are the active workforce today;
the GUI apps become workers only when a structured control channel (or a
justified GUI bridge) exists.
