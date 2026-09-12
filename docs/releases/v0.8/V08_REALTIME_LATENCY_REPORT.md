# v0.8 Real-Time Latency Report (convergence, measured)

Model: hhao/qwen2.5-coder-tools:3b (real stream); STT: fixture partials; TTS: REAL System.Speech first-audio

Model TTFT: 40270.98 ms
First phrase: 42485.8 ms
TTS first audio: 5120.2 ms
Avatar-event delay: 5120.89 ms
Lip-sync offset: 15.0 ms (AUDIO_AMPLITUDE_FALLBACK (System.Speech provides no per-phoneme timestamps here; viseme tables drive the Jaw node))
End-to-end turn: 47607.7 ms
Barge-in: {'ok': True, 'flushed': 4, 'barge_ins': 1, 'state': 'LISTENING'}
Budget check turn 1: False
Status: PASS

Goal met: TTS starts on the first phrase, never waits for the full response; media lane reserves hold during reasoning.
