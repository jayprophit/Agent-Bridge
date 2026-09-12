# v0.8 Modality Matrix (measured on this PC, convergence)

Live probes: windows-ocr PRESENT (en-GB); tesseract absent (not needed);
image endpoints absent; SAPI voices Hazel+Zira present; Ollama present
(qwen3:0.6b, qwen3:1.7b, hhao/qwen2.5-coder-tools:3b).

| Modality | Status | Evidence |
|---|---|---|
| TEXT | AVAILABLE (YES_VERIFIED) | bridge-text local |
| VISION | PROVIDER_REQUIRED | no verified model; route on VERIFIED only |
| OCR | AVAILABLE (YES_VERIFIED) | windows-ocr en-GB fixture roundtrip |
| IMAGE_GENERATION | PROVIDER_REQUIRED | no ComfyUI/A1111 endpoint |
| IMAGE_EDITING | PROVIDER_REQUIRED | same adapter, provenance kept |
| TTS | AVAILABLE (YES_VERIFIED) | System.Speech E2E (319KB WAV this run) |
| STT | NOT_INSTALLED | Whisper slot; interface complete |
| AUDIO_GENERATION | PROVIDER_REQUIRED | no backend |
| VOICE_AGENT | INTERFACE_ONLY | pipeline+streaming+barge-in verified, fixture STT |
| VIDEO_INPUT/OUTPUT | PROVIDER_REQUIRED | no backend |
| 3D_ASSET | AVAILABLE (YES_VERIFIED) | procedural GLB in Three.js, headless Edge |
| AVATAR_3D | AVAILABLE (YES_VERIFIED) | 6/6 browser tests, GLB nodes + states + shot |
| CHARACTER_CREATOR | AVAILABLE (YES_VERIFIED) | 8 modes, simple/advanced, versioning |
| GUIDED_CAMERA_CAPTURE | AVAILABLE (YES_VERIFIED) | fixtures; delete-after-derivation proven |
| CHAT_UI | AVAILABLE (YES_VERIFIED) | session continuity + docking, headless Edge |
| WORK_UI | AVAILABLE (YES_VERIFIED) | agent panel + compact avatar, headless Edge |
| IDE_EMBEDDING | INTERFACE_ONLY | contract only |
| EMAIL | AVAILABLE (YES_VERIFIED) | drafts local; send gated |
| TELEPHONY | AVAILABLE (YES_VERIFIED) | mock lifecycle; PSTN gated |
| RESOURCE_BALANCING | AVAILABLE (YES_VERIFIED) | real workload PASS 2.824s -> 2.334s |
| REALTIME_PIPELINE | AVAILABLE (YES_VERIFIED) | real Ollama stream + real TTS + barge-in |
| LEGACY_MODEL | AVAILABLE (YES_VERIFIED) | 0.6b TEXT_ACTION, 1.7b LEGACY, 3b STRICT_JSON |

Correction vs prior matrix: OCR was NOT_INSTALLED (tesseract probe
only); the OS windows-ocr backend is present and tested, so OCR is
AVAILABLE. No availability faked.
