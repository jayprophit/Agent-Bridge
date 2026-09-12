# Audio Architecture (v0.8, Part C)

Speech synthesis, recognition, generic generation, and transformation are
separate capabilities (TTS is not "audio generation"). TTS: System.Speech
backend VERIFIED (Hazel+Zira; 110KB WAV synthesized locally, no cloud).
STT: no backend (NOT_INSTALLED; Whisper-compatible plugin slot reserved).
Deterministic wave ops (trim/join/normalize/inspect) via stdlib.
See VOICE_AGENT.md for the realtime pipeline.
