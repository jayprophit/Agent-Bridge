# Speech Backend Profile (REQ-p21-speech-profile, P21)

Replaceable, machine-readable, honest speech-backend profile as an
additive leaf over the multimodal router. Owner: Agent-Bridge.

## Parent architecture (surveyed, untouched)

- `multimodal/router.py`: `MultimodalRouter`, `ModalityBackend`
  (backend_id/modality/kind/tool_ids/verified/evidence/limitation),
  TTS/STT modalities, NOT_INSTALLED/PROVIDER_REQUIRED/AVAILABLE
  routing — never by model name.
- `multimodal/stt.py`: `STTBackend` contract + `WhisperCompatibleAdapter`
  plugin contract; no backend bundled (`NOT_INSTALLED` acceptable).
- `multimodal/probes.py`: presence-only probes (tesseract, image
  endpoints, SAPI voice listing) — no downloads.

## Profile (`multimodal/speech_profile.py`)

`SpeechBackendProfile`: backend_profile_id, backend_id, version,
status (INSTALLED/NOT_INSTALLED/AVAILABLE/UNAVAILABLE/UNKNOWN —
router vocabulary, no second taxonomy), capabilities (STT/TTS/STS),
explicit language identifiers, streaming_in/out (support flags, never
performance proof), offline_capable, installed (separate flag),
privacy (factual processing metadata, never compliance claims),
licence (identifier/url/commercial tri-state; open != unrestricted),
consent_required (feature names; REQUIRED != PRESENT, cloning support
!= authorized), provenance (7 classes), evidence_ref.

Rules: PROFILE EXISTS != INSTALLED; INSTALLED != AUTHORIZED;
NOT_INSTALLED != UNSUPPORTED; UNKNOWN != FALSE. Missing backends are
never installed/downloaded/fabricated. No credential fields exist on
the profile (validated + tested). `SpeechProfileRegistry` (validated,
dup-rejecting, idempotent-identical, deterministic).
`attach_profiles` enriches router routes without changing routing.
`detect_sapi_profile` reuses the SAPI list-only probe (present →
INSTALLED offline TTS; absent → NOT_INSTALLED).

P25 authorizes use; P18 owns model metadata (referenced, never
duplicated); P23 UI work out of scope; P27 transport untouched;
Model Fabric stays BLOCKED (no cloud calls/credentials/probes).

## Tests

`tests/test_speech_profile.py` — 11 tests: valid/sparse profiles,
malformed rejection, installed/status coherence, registry semantics,
NOT_INSTALLED honesty, unknown semantics, consent separation,
credential-field absence, router integration unchanged, SAPI
detection mocked both ways.
