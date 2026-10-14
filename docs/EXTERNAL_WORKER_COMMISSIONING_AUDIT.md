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

---

## UPDATE 2 (2026-10-14 ~07:1x) — §12 GUI FALLBACK CORRECTION

Directive f2e40a §12: NO CLI ≠ DEFER. Fall down the control ladder to
accessibility/GUI and TEST. NO CLI cannot jump to UNSUITABLE (§17).

- **antigravity**: AGENT_MODE_VERIFIED via GUI. RUNNING pid 1080; agent
  panel open; model "Gemini 3.8 Flash High"; message ComboBox + Send button
  AX-exposed; workspace chip "base-ui-P0-1"; VS Code lineage → file/terminal/
  test capability by lineage. GUI_CONTROLLABLE; TASK TEST in progress
  (delivery friction: `type` truncates on ComboBox; `set_value` blocked on an
  unanswered approval gate; hotkeys work once a foreground `type` primes the
  Electron window). Not yet WORKER_READY.
- **claude / manus**: NOT RUNNING at 07:1x (were 8696/12604 yesterday) →
  REASSESS ON LAUNCH.
- **cursor**: GUI composer unprobed (CLI_AGENT_MODE closed; GUI_AGENT_MODE
  open per §15).
- deepseek/devin/kimi/qwen/openclaw: progressively probed, one at a time.

Delivery lessons: hotkey combos fail on Electron until a foreground `type`
primes the window; ComboBox composers truncate `type` (paste or set_value
better); the worker session title is the delivery receipt (verify via
`opencode db`, not the keystroke result); duplicate API servers cause a CPU
storm — ONE API with `--state-dir` split from the daemon.
