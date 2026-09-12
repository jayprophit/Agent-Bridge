# Image Provider Architecture (v0.8, Part C)

Canonical `image.*` tools stay provider-neutral. Deterministic stdlib ops
(resize/crop/convert/diagram/annotate/compose) work locally. Generative
paths probe ComfyUI (:8188), A1111/SD WebUI (:7860), or compatible
endpoints; absent -> PROVIDER_REQUIRED. Editing keeps provenance (source,
provider, model, settings, output hash). No model downloads by the bridge.
