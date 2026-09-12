# v0.8 Dependency / Reproducibility Audit (final consolidation)

## Summary

- Python runtime: **stdlib only**. No requirements.txt / setup.py /
  pyproject / Pipfile / package.json anywhere in the repo.
- Third-party Python packages used: **psutil** (optional, graceful
  fallback), **PyYAML** (optional, `_HAS_YAML` guard). Both installed
  here (psutil 7.2.2, pyyaml 6.0.3) but nothing hard-requires them at
  import except `benchmarks/benchmark_runner.py` (top-level psutil;
  benchmark telemetry only).
- Removed-from-stdlib: **audioop** (gone in 3.13). `tools/cat_media.py`
  now degrades those 6 subtools to clean NOT_INSTALLED (verified).
- `win32com` referenced only inside a guarded acceptance probe
  (run_windows_v07_acceptance.py); production TTS uses System.Speech
  via PowerShell, not win32com.
- OS-provided (Windows): PowerShell 5.1+, System.Speech (SAPI voices),
  WinRT OCR, Edge/Chrome (browser acceptance only).
- External services (all optional/provider-gated): Ollama server
  127.0.0.1:11434 (live-model acceptance), ComfyUI/A1111 (absent),
  Whisper/STT (absent), PSTN (absent).

## Pinning

No floating ranges exist (no dependency files at all). Interpreter:
CPython 3.13.14 (MSC v.1944 AMD64). Recommended: `pip install
"psutil==7.2.2"` for full telemetry; core runs without it.
Do not hard-pin OS components (SAPI/WinRT/Edge/Ollama) in-repo.

## Clean-machine test: CLEAN_INSTALL_VERIFIED (core)

Bare venv (`--without-pip`, zero installs), repo as CWD:
`test_resources + test_compat + test_realtime + test_avatar_creator +
test_avatar_capture + test_repo_portability + test_secret_hygiene` =
**87 tests, OK**. No old-root access, no undeclared modules, no hidden
fixes. Full telemetry/benchmarks/browser/live-model paths additionally
need psutil / Edge / Ollama as documented in docs/REPRODUCIBLE_SETUP.md.

## SBOM

SBOM_STATUS = DEPENDENCY_MANIFEST (CycloneDX/SPDX tooling not installed;
manifest is the v0.8 record). Machine detail: DEPENDENCY_MANIFEST.json.
No local advisory DB available; versions recorded; no known advisories
checked in (nothing fetched from network for this audit).
