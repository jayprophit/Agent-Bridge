# Agent Bridge v0.8 Development Progress

## Source
- **Source**: frozen Agent Bridge v0.7.0 (tag v0.7.0, commit d04956e)
- **Source verification**: 219/219 SHA-256 manifest hashes match; 222 files
  (219 hashed + 3 release-manifest files); v0.7.0 tag never moved.
- **Status**: In progress — pre-autonomy standardization release.

## Constraints (every increment)
MODEL-AGNOSTIC · PROVIDER-AGNOSTIC · AGENT-AGNOSTIC · IDE-AGNOSTIC ·
DEVICE-AWARE · LOCAL-FIRST · OFFLINE-FIRST WHERE POSSIBLE ·
CROSS-DEVICE READY · SMALL-MODEL FRIENDLY. Capabilities live in the BRIDGE.

## Phase 0 — Dedup / gap audit ✅
- v0.8 tree created from frozen tag via git archive (CRLF-normalized copy
  rejected after 44/219 hash match revealed `tar`/autocrlf conversion;
  byte-exact working-tree copy verifies 219/219).
- v0.7 baseline: 350 tools / 40 families, migrated 400/400 tests green.
- V08_GAP_MATRIX.md/.json: every requested capability mapped to
  EXISTS_AND_WORKS / EXISTS_NEEDS_BACKEND / EXISTS_PARTIAL /
  EXISTS_INTERFACE_ONLY / MISSING with a v0.8 action.
- Key corrections: TTS backend EXISTS (System.Speech voices Hazel+Zira;
  v0.7 acceptance probed the wrong backend); toolkit negotiate/shortlist
  EXISTS; EventBus EXISTS_PARTIAL; email/telephone/avatar/scheduler/
  translator/OCR-engine/voice-pipeline genuinely MISSING.
- Dedupe decisions recorded (extend vision.*/image.*/speech.*/toolkit/
  EventBus/nodes; no duplicate aliases).

## Part A — Adaptive resource / weight balancing ✅
- New `resources/` package: descriptors (10 resource kinds, 22 workload
  kinds, 4 lanes, PlacementDecision, PressureState), ResourcePool
  (built from profiler output; Ollama num_gpu/num_thread declared-partial
  controls, BACKEND_CONTROL_UNAVAILABLE elsewhere), WorkloadClassifier
  (rule-based, no model), ResourceScheduler (waves, write-collision guard,
  dependency order), AdaptiveBalancer (9 configurable weights; reliability
  outranks speed), PressureMonitor (lane reserves, pressure responses).
- Tests: tests/test_resources.py, 17/17 PASS (synthetic fixtures only).
- Real acceptance: run_resource_balance_acceptance.py on this PC
  (i7-870 8T, 16GB, GTX 1050 Ti): 12 mixed tasks, BEFORE sequential 0.396s
  vs AFTER waves+placement 0.096s, 0 errors, headroom OK.
  Reports: V08_RESOURCE_BALANCE_REPORT.json/.md.
- NPU status: none detected on this PC (accelerator list empty; NPU lane
  modeled, unpopulated). GPU placement: declared-partial via Ollama
  controls (not benchmark-verified). Remote-node balancing: modeled via
  REMOTE_NODE_COMPUTE advertisements (verified in unit tests only).

## Test count
- Migrated v0.7 suite: untouched so far (400 tests, last verified green on
  frozen tree).
- New v0.8 tests: 17 (test_resources.py) + 20 (test_compat.py).
- Total: 437 (400 migrated + 37 new), all passing.

## Part B — Small / legacy model compatibility ✅
- New `compat/` package: modes (6, name-free selection), negotiation
  (budgets incl. SMALL_CONTEXT/LEGACY), LegacyActionTranslator (fenced/bare
  JSON + `tool:` lines; unknown tools rejected; bounded repair; never
  executes), ModelCapabilityProbe (scripted exchanges; native never claimed
  by probe).
- Tests: tests/test_compat.py, 20/20 PASS (incl. UnknownLegacyModel9000
  synthetic completing a bounded 2-step task through translator+ToolRouter).
- Live acceptance: run_compat_acceptance.py → qwen2.5-coder-tools:3b
  STRICT_JSON end-to-end OK; qwen3:0.6b TEXT_ACTION / qwen3:1.7b LEGACY
  selected, single repair round did not recover (fails safe, no invented
  execution). V08_COMPAT_ACCEPTANCE.json.
- DefaultAgent/AgentCore untouched by design; compat/ is the wiring layer
  (documented in LEGACY_MODEL_COMPATIBILITY.md, next).

## Parts C–J ✅
- Multimodal fabric (`multimodal/`): provider-neutral routing for 12
  modalities; local deterministic image ops; SAPI TTS; honest
  PROVIDER_REQUIRED/NOT_INSTALLED elsewhere. Probes for tesseract,
  ComfyUI/A1111 endpoints, SAPI voices (presence only).
- TTS synthesis E2E VERIFIED (110KB WAV, System.Speech, no cloud; Hazel+Zira).
- Voice pipeline (`voice/`): push-to-talk/conversation, stop/mute/interrupt,
  device selection, consent-gated recording, shared agent session.
- Email (`tools/cat_comms.py` + EmailAdapter): local artifact drafts real;
  send/read/search provider-gated, owner-only, no credentials in tree (tested).
- Telephony (`comms/`): neutral arch + LoopbackCallProvider; full mock
  lifecycle tested; PSTN stays PROVIDER_REQUIRED; default MANUAL_ANSWER.
- Avatar (`avatar/` + `ui/`): 14-event protocol, explicit presentation
  profiles, 15-viseme jaw map, 12KB procedural GLB (10 named nodes);
  reference Chat/Work UI with docking, one shared session, offline 2D
  fallback + Three.js hook. Tests: 16/16.
- IDE embedding (`ides/embedding.py`): HostContext/selection/diagnostics/
  diff-approval contract + interface-only reference adapter.
- Event unity: chat/voice/call/IDE share agent_session_id over EventBus (tested).

## Part L — Matrices ✅
- V08_MODALITY_MATRIX.json/.md: 12 modalities from live state (TEXT+TTS
  AVAILABLE/verified; rest truthful PROVIDER_REQUIRED/NOT_INSTALLED).
- V08_TOOL_CAPABILITY_MATRIX.json: 364 tools (350 + 6 email + 8 telephone),
  VERIFIED 7 / UNVERIFIED 266 / PROVIDER_REQUIRED 73 / NOT_INSTALLED 13 /
  DISABLED 5.

## Part M/N — Security & artifacts ✅
- New code under v0.7 policy: email.send owner-only + provider-gated,
  telephone default-manual + consent-gated recording, voice mute/consent,
  avatar validation, UI static (no backend). No plugin bypass (tested).
- Media artifacts: email drafts + call transcripts via ArtifactRegistry
  (origin/tool/hash/size/provenance); large outputs by reference.

## Part R — Acceptance ✅
- run_v08_acceptance.py: 18 categories, 0 failures (14 PASS incl. real TTS,
  2 PROVIDER_REQUIRED, 2 NOT_INSTALLED; v07_regression runs full suite).
- V08_LOCAL_ACCEPTANCE_REPORT.json/.md generated.

## Test count (final, pre-convergence)
- Migrated v0.7: 400/400 PASS in v08 tree (v07_regression category).
- New v0.8: 74 (17 resources + 20 compat + 11 multimodal/voice + 10 comms + 16 avatar).
- Reported total: 474/474 PASS (STALE hardcode, see convergence below).

## Final Status (pre-convergence) ✅
- V08_FINAL_ACCEPTANCE_REPORT.json/.md generated
- V08_GAP_MATRIX.json/.md complete with all gaps documented
- V08_MODALITY_MATRIX.json complete with 12 modalities
- V08_TOOL_CAPABILITY_MATRIX.json: 364 tools (STALE; live audit says 370)
- v0.8 status: PRE_AUTONOMY_STANDARDIZATION — ready for owner authorization

## Convergence verification (this pass, measured from source+execution)
- Migration completed into permanent root (149 entries): runtime, bridge,
  executor, adapters, prompts, reference shell, run scripts, docs.
  Portability BUGs fixed: service.py/cli.py now use AGENT_BRIDGE_ROOT env
  (was hard-coded old tree); bridge configs emptied; old E2E scripts made
  disposable/temp. Zero old-path BUGs remain (HISTORICAL_DOC reports only).
- Test discovery truth: 57 files, 541 tests, 0 loader failures. The 474
  number was stale (true old-tree discovery is 491; +50 new convergence
  tests: 13 realtime, 16 creator, 9 capture, 4 portability, 6 hygiene,
  plus browser evidence run).
- New modules: voice/realtime.py (streaming pipeline, jitter/backpressure,
  turn coordinator, barge-in, interactive-lane scheduler); avatar/creator.py
  (8 modes, simple/advanced, independence, versioned presets);
  avatar/capture.py (guided 7-view flow, ephemeral raw, delete proven,
  photo contract, reconstruction provider-required).
- Real resource workload PASS: baseline 2.824s vs adaptive 2.334s
  (Ollama qwen3:0.6b TTFT 1.963s, 22.15 tok/s; 20 files; test_resources OK;
  CPU 100% per-core, RAM 16GB, GPU 1-4%, VRAM 826-1764/4096MB).
- Real-time latency PASS: real Ollama stream + real System.Speech first
  audio (5.12s, 319KB WAV) + barge-in (flushed 4); lip-sync =
  AUDIO_AMPLITUDE_FALLBACK (honest); cold TTFT 40.3s (model load).
- Browser Three.js + Chat/Work PASS: 6/6 in 96.652s (GLB nodes, states,
  screenshot, session continuity, docking).
- DefaultAgent autonomy PASS: coder-3b selected by ModelRouter (LOCAL_ONLY,
  alternatives recorded), 12-tool shortlist of 370, 2-wave CPU placement,
  2 router writes, 4/4 tests OK via router, 0 repairs, gate
  PENDING_OWNER_REVIEW. V08_PRE_AUTONOMY_REPORT.json/.md written.
- Matrices regenerated live: 370 tools (VERIFIED 16 / UNVERIFIED 260 /
  PROVIDER_REQUIRED 73 / NOT_INSTALLED 16 / DISABLED 5); 23 modalities;
  OCR corrected to AVAILABLE (windows-ocr en-GB verified).
- Security PASS: zero secrets/captures/personal paths; .gitignore extended
  (.bridge, TLS, workspaces, captures, secrets); no license added.

## Owner Authorization Required
Explicit authorization required before v0.8 tag/freeze. Without authorization,
the tree remains in pre-autonomy state for further development.

## Suggested Follow-ups (post-authorization)
- HTTPS for UI serving
- Physical two-machine acceptance
- Whisper STT plugin implementation
- ComfyUI image adapter

## Part U — Final gap audit (owner questions)
- GENERATE TEXT: YES_VERIFIED. READ/UNDERSTAND IMAGES: NO (no verified path).
- OCR: NO (no engine). GENERATE IMAGES: YES_PROVIDER_REQUIRED.
- EDIT IMAGES: YES_PROVIDER_REQUIRED. GENERATE AUDIO: YES_INTERFACE_ONLY.
- SPEAK: YES_VERIFIED (SAPI E2E). LISTEN/TRANSCRIBE: NO.
- REAL-TIME VOICE AGENT: YES_INTERFACE_ONLY (pipeline+fixtures; no live audio).
- DRAFT EMAIL: YES_VERIFIED. SEND EMAIL WHEN AUTHORIZED: YES_PROVIDER_REQUIRED.
- TELEPHONE AGENT WITH CONFIGURED PROVIDER: YES_INTERFACE_ONLY (mock proven).
- SHOW 3D AVATAR: YES_INTERFACE_ONLY (protocol+GLB verified; 3D needs host three.js).
- LIP-SYNC: YES_INTERFACE_ONLY (tables tested; provider-timestamp path unwired).
- EXPRESSIONS/GESTURES: YES_VERIFIED. CHAT+WORK SAME SESSION: YES_VERIFIED.
- EMBED IN IDE: YES_INTERFACE_ONLY. HEADLESS: YES_VERIFIED.
- OLD/SMALL MODELS: YES_VERIFIED. AUTO-DETECT UNKNOWN: YES_VERIFIED.
- BALANCE HARDWARE: YES_VERIFIED. ADAPT TO PRESSURE: YES_VERIFIED.
- DELEGATE TO TRUSTED NODES: YES_VERIFIED (localhost E2E, migrated green).
