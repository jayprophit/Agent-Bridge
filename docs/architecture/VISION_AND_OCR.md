# Vision and OCR (v0.8, Part C)

Vision routes only to VERIFIED or appropriately declared backends (none
verified on this PC; qwen3.5 stays PROVIDER_REPORTED/FAILED_PROBE). OCR
resolution order: OS-native -> installed engine (tesseract: absent) ->
vision-model fallback -> remote provider if policy permits; each returns
text + confidence/boxes where supplied, else NOT_INSTALLED. No name-based
inference anywhere.
