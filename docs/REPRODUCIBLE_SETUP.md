# Agent Bridge — Reproducible Setup (v0.8)

## Assumptions

- OS: Windows 10/11 (primary, all acceptance measured here). Linux/macOS:
  core stdlib paths work; SAPI TTS / WinRT OCR / Edge CDP are Windows-only
  and degrade to honest NOT_INSTALLED elsewhere.
- Python: CPython 3.13 (verified 3.13.14). No other runtime needed. UI:
  any modern browser (vendored three.js, no CDN).

## Install

```powershell
git clone https://github.com/jayprophit/Agent-Bridge.git
cd Agent-Bridge
# core needs NOTHING else (stdlib only). Optional telemetry:
pip install "psutil==7.2.2"
# Optional live-model paths:
# install Ollama and pull: qwen3:0.6b, qwen3:1.7b, hhao/qwen2.5-coder-tools:3b
```

Environment: `AGENT_BRIDGE_ROOT` (workspace default; falls back to `.`).
No secrets, no tokens, no account required.

## Run

```powershell
python -m unittest discover -s tests -p "test_*.py"   # full suite (541)
python scripts/run_v08_acceptance.py                    # 18-category acceptance
python bridge.py --help                                 # CLI
python service.py --root <dir>                          # local /v1 service (127.0.0.1)
```

## External prerequisites (only for the paths that need them)

| Path | Needs | Without it |
|---|---|---|
| unit/core tests | nothing | — |
| benchmark telemetry | psutil | graceful fallback |
| browser avatar/UI tests | Edge/Chrome | honest skip/fail, core unaffected |
| live-model/compat/autonomy | Ollama + models | fixtures/synthetic probes |
| TTS | System.Speech voices | NOT_INSTALLED |
| OCR | WinRT/tesseract | NOT_INSTALLED |
| images | ComfyUI/A1111 | PROVIDER_REQUIRED |
