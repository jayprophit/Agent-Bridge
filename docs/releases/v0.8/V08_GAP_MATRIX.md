# v0.8 Gap Matrix (Phase 0 — deduplication audit)

Source: frozen v0.7.0 (350 tools, 40 families). Rule: EXTEND existing tools;
never duplicate (no `vision.read_image` beside `vision.*`, no `email.send_v2`).

## Part A — Adaptive resource / weight balancing

| Requested | Existing v0.7 | Backend | Gap | v0.8 action |
|---|---|---|---|---|
| ResourceDescriptor/Pool | DeviceCapabilityProfile (device/) | psutil/WMI probes | No pool abstraction | NEW `resources/` package |
| ResourceMonitor (live) | Benchmark ResourceMonitor (per-run snapshots) | psutil | No continuous monitor | EXTEND into continuous monitor |
| WorkloadClassifier | ModelRouter task types (partial) | — | No workload taxonomy | NEW classifier |
| ResourceScheduler/AdaptiveBalancer | RuntimeTuner + CalibrationEngine (placement inputs) | — | No scheduler/balancer | NEW scheduler + balancer |
| Pressure response | Tuner RAM/VRAM pressure handling | psutil | No live pressure loop | NEW PressureMonitor |
| Parallel execution | Executor dispatch (sequential assumed) | — | No dependency-aware parallelism | NEW (bounded, collision-safe) |
| CPU/GPU/NPU placement | HardwareProfiler detects; Ollama offload not controlled | Ollama/Vulkan/DirectML | No offload control; record BACKEND_CONTROL_UNAVAILABLE where true | NEW lane model, honest controls |

## Part B — Small / legacy model compatibility

| Requested | Existing v0.7 | Backend | Gap | v0.8 action |
|---|---|---|---|---|
| Tool shortlisting | tools/toolkit.py `negotiate` + `short_schemas` | registry | EXISTS_AND_WORKS; needs wiring into agent loop | EXTEND DefaultAgent/AgentCore |
| Compatibility modes | capability_evidence + tool_calling_mode (4 modes) | benchmarks | No runtime mode selection | NEW negotiation layer |
| Legacy action translator | none | — | MISSING | NEW constrained parser + bounded repair |
| Capability probe | benchmark capability tests | Ollama | EXISTS_PARTIAL; automate at registration | EXTEND |
| SMALL_CONTEXT_MODE | context_length metadata | — | No context budgeting | NEW |

## Part C — Multimodal fabric

| Requested | Existing v0.7 | Backend | Gap | v0.8 action |
|---|---|---|---|---|
| TEXT | full stack | Ollama | EXISTS_AND_WORKS | — |
| VISION | vision.* (MODEL_REQUIRED interface) | none verified | No verified backend | Route only on VERIFIED; keep truthful |
| OCR | none (vision.detect_text is an interface) | none | MISSING backend | OS/engine probe; vision fallback; else NOT_INSTALLED |
| IMAGE_GENERATION | image.generate (PROVIDER_REQUIRED) | none local | No local endpoint | Adapter for ComfyUI/A1111/compatible; else PROVIDER_REQUIRED |
| IMAGE_EDITING | image.edit (PROVIDER_REQUIRED) | none | Same as generation | Same adapter + provenance |
| AUDIO_GENERATION | audio.generate (NOT_INSTALLED) | none | MISSING | Keep honest; plugin slot only |
| TTS | speech.tts (System.Speech backend) | SAPI voices Hazel+Zira; synthesis E2E VERIFIED (110KB WAV, System.Speech, no cloud) | EXISTS_AND_WORKS (v0.7 acceptance had probed win32com — wrong probe, corrected) | Wire into voice pipeline output |
| STT | speech.stt (NOT_INSTALLED) | none | MISSING backend | Plugin slot (Whisper-compatible); else NOT_INSTALLED |
| REALTIME_VOICE | none | — | MISSING pipeline | NEW voice agent (Part D) |
| VIDEO_INPUT/OUTPUT | video.* NOT_INSTALLED | none | MISSING | Honest statuses only |
| 3D_ASSET | none | — | MISSING | Part G |

## Part D — Voice agent

| Requested | Existing v0.7 | Backend | Gap | v0.8 action |
|---|---|---|---|---|
| Voice pipeline/session | none; events.EventBus/EventLogger exist | SAPI TTS only | MISSING pipeline | NEW voice/ package on EventBus |
| VAD/barge-in/mute/devices | microphone/speaker presence detected | — | No audio capture backend | Fixture-driven; no fake capture |

## Part E/F — Email / telephony

| Requested | Existing v0.7 | Backend | Gap | v0.8 action |
|---|---|---|---|---|
| email.* | NONE (no email tools exist) | — | MISSING | NEW canonical email.* (draft/compose local; send approval-gated, no credentials in tree) |
| telephony | NONE | — | MISSING | NEW provider-neutral telephony arch + loopback mock provider; PSTN stays PROVIDER_REQUIRED |

## Part G/H/I — Avatar / UI / IDE embedding

| Requested | Existing v0.7 | Backend | Gap | v0.8 action |
|---|---|---|---|---|
| Avatar events/protocol | none | — | MISSING | NEW event protocol (backend-agnostic) |
| Three.js renderer | none (reference_agent_shell is a mock shell) | — | MISSING | NEW reference web UI (Three.js isolated from runtime) |
| Chat/Work views + docking | none | — | MISSING | NEW reference UI, same-session switching |
| IDE embedding contract | ides/ registry+router+discovery | — | Protocol MISSING | NEW embedding contract doc + reference adapter shape |

## Part J — Unified session/event bus

| Requested | Existing v0.7 | Backend | Gap | v0.8 action |
|---|---|---|---|---|
| Event bus | events.EventBus/EventLogger | in-process | EXISTS_PARTIAL (not shared across chat/voice/IDE/remote) | EXTEND to unified bus |

## Part K — External model/agent plug-in

| Requested | Existing v0.7 | Backend | Gap | v0.8 action |
|---|---|---|---|---|
| Unknown future models/agents/IDEs | registries + discovery + negotiation | — | EXISTS_AND_WORKS (pattern proven) | Synthetic FutureModel9000-class tests per feature |

## Duplicates avoided (dedup decisions)

- No new vision-read tool: EXTEND `vision.*`.
- No new image tools: EXTEND `image.*` with provider adapters.
- No new TTS/STT tools: EXTEND `speech.*` (fix acceptance probe to System.Speech).
- No new search/shortlist tool: EXTEND `tools/toolkit.py` negotiation.
- No new event system: EXTEND `events.EventBus`.
- No new pairing/transport: EXTEND `nodes/` transports.
- Email/telephone/avatar/scheduler/translator/OCR-engine/voice-pipeline: genuinely MISSING, new code justified.
