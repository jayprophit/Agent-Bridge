"""WorkloadClassifier (v0.8). Rule-based task -> workload mapping.

No model required: keyword + requirement rules. Small-model friendly.
"""
from __future__ import annotations

from resources.descriptors import (
    AUDIO_PROCESSING, BACKGROUND_INDEXING, BROWSER_RENDERING, CACHE_BUILD,
    CODE_ANALYSIS, COMPILATION, DATABASE_QUERY, EMBEDDINGS, FILE_ANALYSIS,
    IMAGE_GENERATION, MODEL_INFERENCE, NETWORK_TRANSFER, OCR, RAG_INDEXING,
    RENDER_3D, STT, TESTING, TOKENIZATION, TTS, VIDEO_DECODE, VIDEO_ENCODE,
    VISION, WorkloadDescriptor, LANE_BACKGROUND, LANE_BALANCED,
)

_RULES: list[tuple[str, tuple[str, ...]]] = [
    (MODEL_INFERENCE, ("infer", "generate text", "complete", "chat", "prompt")),
    (TOKENIZATION, ("tokenize", "tokens", "detokenize")),
    (EMBEDDINGS, ("embed", "embedding", "vectorize")),
    (RAG_INDEXING, ("rag index", "index documents", "ingest docs")),
    (FILE_ANALYSIS, ("analyze file", "read file", "inspect file", "lint file")),
    (CODE_ANALYSIS, ("analyze code", "refactor", "review code", "debug")),
    (COMPILATION, ("compile", "build project", "transpile")),
    (TESTING, ("run tests", "pytest", "unittest", "test suite", "coverage")),
    (OCR, ("ocr", "extract text from image", "read text in")),
    (VISION, ("image", "picture", "photo", "screenshot", "see", "look at")),
    (IMAGE_GENERATION, ("generate image", "draw", "text-to-image", "imagine")),
    (AUDIO_PROCESSING, ("audio", "normalize audio", "convert audio")),
    (TTS, ("speak", "say aloud", "text-to-speech", "read aloud", "tts")),
    (STT, ("transcribe", "speech-to-text", "dictation", "stt")),
    (VIDEO_ENCODE, ("encode video", "transcode", "compress video")),
    (VIDEO_DECODE, ("decode video", "extract frames")),
    (RENDER_3D, ("render 3d", "render avatar", "raytrace")),
    (BROWSER_RENDERING, ("browser", "web page", "render page")),
    (DATABASE_QUERY, ("sql", "query table", "database")),
    (NETWORK_TRANSFER, ("download", "upload", "fetch url", "transfer")),
    (CACHE_BUILD, ("build cache", "warm cache", "cache assets")),
    (BACKGROUND_INDEXING, ("background index", "reindex", "watch files")),
]


class WorkloadClassifier:
    """Maps task text + requirements to WorkloadDescriptors."""

    def __init__(self, default_lane: str = LANE_BALANCED):
        self.default_lane = default_lane
        self._counter = 0

    def classify(self, task_text: str, requirements: dict | None = None,
                 lane: str = "") -> list[WorkloadDescriptor]:
        """Return 1+ workloads for a task (multi-kind tasks split)."""
        requirements = dict(requirements or {})
        text = (task_text or "").lower()
        matched: list[str] = []
        for kind, keywords in _RULES:
            if any(kw in text for kw in keywords):
                matched.append(kind)
        if not matched:
            matched = [MODEL_INFERENCE]
        out = []
        for kind in matched:
            self._counter += 1
            out.append(WorkloadDescriptor(
                workload_id=f"wl-{self._counter:04d}",
                kind=kind,
                display_name=f"{kind} from task",
                min_ram_mb=int(requirements.get("min_ram_mb", 0) or 0),
                min_vram_mb=int(requirements.get("min_vram_mb", 0) or 0),
                needs_gpu=bool(requirements.get("needs_gpu", False)),
                backend=str(requirements.get("backend", "") or ""),
                priority=int(requirements.get("priority", 50)),
                lane=lane or self.default_lane,
                writes_files=list(requirements.get("writes_files", []) or []),
                depends_on=list(requirements.get("depends_on", []) or []),
            ))
        # Background-flavored tasks default to the background lane.
        if any(k in text for k in ("background", "watch", "reindex", "nightly")):
            for w in out:
                if w.lane == self.default_lane:
                    w.lane = LANE_BACKGROUND
        return out
