# v0.7 Known Limitations (freeze)

## NON_BLOCKING_LIMITATION

- Physical cross-device validation not performed (DEVICE_REQUIRED);
  localhost E2E verified instead.
- No TLS certificates shipped; HTTPS needs operator-provided certs
  (CONFIGURATION_REQUIRED).
- No WebSocket backend (NOT_INSTALLED / INTERFACE_ONLY); SSE covers streams.
- Windows Credential Manager adapter is INTERFACE_ONLY (dev file store only).
- Mutual TLS lifecycle not implemented (SUPPORTED_CONFIGURATION).
- q4 vs q8 quantization comparison: INSUFFICIENT_EVIDENCE (no downloads).
- IMPLEMENTED_VERIFIED tool states are strict (exact test references only);
  most AVAILABLE tools with real backends are IMPLEMENTED_UNVERIFIED.
- Camera permission state unknown (presence-only detection by design).
- RAM attribution ESTIMATED when the provider process is not matchable.
- Vision: no verified vision model (qwen3.5 PROVIDER_REPORTED, live probe failed).
- Installed-runtime and camera/microphone-permission detection not implemented.

## PROVIDER_REQUIRED (truthful, not failures)

- 67 tools (github.*, cloud/remote families); TTS/STT/image/video/OCR backends.

## DEVICE_REQUIRED

- Second physical machine; camera permission probing.

## CONFIGURATION_REQUIRED

- HTTPS certificates; cloud credentials; image-generation server.

## FUTURE_VERSION

- Small-model prompt profiles; NodeRegistry physical acceptance;
  OWNER_FULL_ACCESS remote-policy review beyond the default-deny gate.
