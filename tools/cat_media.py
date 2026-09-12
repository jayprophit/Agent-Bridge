"""Adapter catalog, batch 5: vision/ocr/image/video/audio/speech/
predictive/text/computer/ide."""
from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any

from tools.adapter import ToolAdapter
from tools.cat_core import OWNER_ONLY, SAFE_PROFILES, _rec
from tools.cat_data import _Ctx
from tools.registry import (AVAILABLE, MODEL_REQUIRED, MUTATING_LOCAL,
                            NOT_INSTALLED, PROVIDER_REQUIRED, READ_ONLY,
                            SAFE_LOCAL, UNAVAILABLE, ToolRecord)

try:  # removed from stdlib in Python 3.13; WAV edit/analysis needs it
    import audioop as _audioop
    _HAS_AUDIOOP = True
except ImportError:
    _audioop = None
    _HAS_AUDIOOP = False

_AUDIOOP_SUBS = frozenset(("convert", "trim", "join", "normalize",
                           "frequency", "waveform", "spectrum"))
_AUDIOOP_UNAVAILABLE = {"ok": False, "status": NOT_INSTALLED,
                        "error": "audioop unavailable on this Python "
                                 "(removed in 3.13+); WAV inspect/play "
                                 "still work"}


class VisionAdapter(_Ctx):
    def probe(self):
        # honest live check would load a 2B model; use cached inventory:
        # qwen3.5 advertises vision but returned EMPTY on a live image probe
        # (2026-09-10), so text-only remains the truthful default.
        return {"available": False, "status": MODEL_REQUIRED,
                "reason": "no vision-capable model verified (qwen3.5 vision "
                          "advertised but empty on live probe); DOM tools work"}

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        if sub == "inspect_image" and context and \
                context.get("vision_verified"):
            return {"ok": False, "status": MODEL_REQUIRED,
                    "error": "verified vision backend not wired in v0.7"}
        return {"ok": False, "status": MODEL_REQUIRED,
                "error": f"vision.{sub} needs a verified vision-capable model"}


def vision_records() -> list[ToolRecord]:
    return [_rec(f"vision.{s}", "vision", s, f"vision.{s} (interface)",
                 "none", READ_ONLY, status=MODEL_REQUIRED, available=False,
                 installed=False, requires_model_capability="vision",
                 tags=("vision",), inschema={"type": "object"})
            for s in ("inspect_image", "inspect_screenshot", "detect_text",
                      "detect_objects", "describe", "compare", "diagram",
                      "chart", "ui_elements", "ocr")]


class ImageAdapter(_Ctx):
    def probe(self):
        det = {"generate": False, "provider": ""}
        try:
            import urllib.request
            for url in ("http://127.0.0.1:7860/", "http://127.0.0.1:8188/"):
                try:
                    urllib.request.urlopen(url, timeout=3)
                    det = {"generate": True,
                           "provider": f"local image server at {url}"}
                    break
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
        return {"available": True, "status": AVAILABLE,
                "deterministic": ["resize", "crop", "convert", "diagram",
                                  "annotate-svg", "compose-svg"],
                "generative": det}

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        if sub == "generate":
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    "error": "image.generate needs a local image provider "
                             "(none detected)"}
        if sub in ("edit", "enhance", "upscale", "remove_background"):
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    "error": f"image.{sub} is generative: provider required"}
        if sub in ("resize", "crop", "convert"):
            return self._raster(arguments, sub)
        if sub in ("diagram", "annotate", "compose"):
            return self._svg(arguments, sub)
        return {"ok": False, "error": f"unknown image subtool: {sub!r}"}

    def _read_png(self, path: Path):
        import struct
        import zlib
        data = path.read_bytes()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("not a PNG file")
        pos, w, h, bitd, ctype, pixels = 8, 0, 0, 0, 0, b""
        while pos < len(data):
            ln = struct.unpack(">I", data[pos:pos + 4])[0]
            typ, chunk = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + ln]
            if typ == b"IHDR":
                w, h, bitd, ctype, _, _, _ = struct.unpack(">IIBBBBB", chunk)
            elif typ == b"IDAT":
                pixels += chunk
            pos += 12 + ln
        if bitd != 8 or ctype != 2:
            raise ValueError("only 8-bit RGB PNG supported")
        import array
        raw = zlib.decompress(pixels)
        stride = w * 3
        rows, prev, out = [], bytearray(stride), bytearray()
        for y in range(h):
            f = raw[y * (stride + 1)]
            cur = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
            if f == 1:
                for i in range(3, stride):
                    cur[i] = (cur[i] + cur[i - 3]) & 255
            elif f == 2:
                for i in range(stride):
                    cur[i] = (cur[i] + prev[i]) & 255
            elif f not in (0,):
                raise ValueError(f"unsupported PNG filter {f}")
            out += cur
            prev = cur
            rows.append(bytes(cur))
        return w, h, rows

    def _write_png(self, path: Path, w: int, h: int, rows: list[bytes]) -> None:
        import binascii
        import struct
        import zlib

        def chunk(tag: bytes, data: bytes) -> bytes:
            c = tag + data
            return struct.pack(">I", len(data)) + c + struct.pack(
                ">I", binascii.crc32(c) & 0xFFFFFFFF)

        raw = b"".join(b"\x00" + r for r in rows)
        ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                         + chunk(b"IDAT", zlib.compress(raw))
                         + chunk(b"IEND", b""))

    def _raster(self, arguments, sub):
        try:
            src = self._resolve(str(arguments.get("path", "")))
            dest = self._resolve(str(arguments.get("dest", "")))
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"path refused: {e}"}
        if not src.is_file():
            return {"ok": False, "error": "source not found"}
        try:
            w, h, rows = self._read_png(src)
        except (OSError, ValueError) as e:
            return {"ok": False, "error": f"raster read failed: {e}"}
        if sub == "resize":
            nw = int(arguments.get("width", w))
            nh = int(arguments.get("height", h))
            if nw <= 0 or nh <= 0 or nw > 4096 or nh > 4096:
                return {"ok": False, "error": "bad dimensions"}
            new = []
            for y in range(nh):
                sy = min(h - 1, int(y * h / nh))
                row = bytearray()
                for x in range(nw):
                    sx = min(w - 1, int(x * w / nw)) * 3
                    row += rows[sy][sx:sx + 3]
                new.append(bytes(row))
            w, h, rows = nw, nh, new
        elif sub == "crop":
            try:
                x, y, cw, ch = (int(arguments.get(k, 0))
                                for k in ("x", "y", "width", "height"))
            except (TypeError, ValueError):
                return {"ok": False, "error": "crop needs x/y/width/height"}
            if cw <= 0 or ch <= 0 or x < 0 or y < 0 or x + cw > w or y + ch > h:
                return {"ok": False, "error": "crop rectangle out of range"}
            rows = [r[x * 3:(x + cw) * 3] for r in rows[y:y + ch]]
            w, h = cw, ch
        elif sub == "convert":
            fmt = str(arguments.get("format", "png")).lower()
            if fmt != "png":
                return {"ok": False, "status": PROVIDER_REQUIRED,
                        "error": f"convert to {fmt!r} needs an image backend"}
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            self._write_png(dest, w, h, rows)
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "path": str(dest), "size": [w, h],
                "verified": dest.exists()}

    def _svg(self, arguments, sub):
        kind = str(arguments.get("kind", "diagram"))
        body = str(arguments.get("body", arguments.get("text", "")))[:5000]
        if kind == "mermaid":
            svg = ("<svg xmlns='http://www.w3.org/2000/svg' width='600' "
                   "height='200'><text x='10' y='30' font-family='monospace'>"
                   + body.replace("&", "&amp;").replace("<", "&lt;")[:2000] +
                   "</text></svg>")
        else:
            svg = ("<svg xmlns='http://www.w3.org/2000/svg' width='600' "
                   f"height='200'><text x='10' y='30'>{body[:2000]}</text></svg>")
        dest = str(arguments.get("dest", ""))
        if dest:
            try:
                target = self._resolve(dest)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(svg, encoding="utf-8")
                return {"ok": True, "path": str(target),
                        "verified": target.exists()}
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"path refused: {e}"}
        return {"ok": True, "svg": svg[:20000]}


def image_records() -> list[ToolRecord]:
    out = [_rec("image.generate", "image", "generate",
                "image.generate (needs provider)", "none", MUTATING_LOCAL,
                status=PROVIDER_REQUIRED, available=False, installed=False,
                provider="local image server (none detected)",
                tags=("image", "generate"), inschema={"type": "object"},
                needs_install="local image server (SD/ComfyUI)")]
    for tid, risk in (("image.edit", MUTATING_LOCAL), ("image.resize", MUTATING_LOCAL),
                      ("image.crop", MUTATING_LOCAL), ("image.convert", MUTATING_LOCAL),
                      ("image.remove_background", MUTATING_LOCAL),
                      ("image.enhance", MUTATING_LOCAL),
                      ("image.annotate", MUTATING_LOCAL),
                      ("image.upscale", MUTATING_LOCAL),
                      ("image.compose", MUTATING_LOCAL),
                      ("image.diagram", READ_ONLY)):
        real = tid in ("image.resize", "image.crop", "image.convert",
                       "image.diagram", "image.annotate", "image.compose")
        # annotate/compose are SVG-based (real); generative peers need providers
        if tid in ("image.annotate", "image.compose"):
            real = True
        if real:
            out.append(_rec(tid, "image", tid.split(".")[1], tid, "stdlib",
                            risk, tags=("image",),
                            inschema={"type": "object"}))
        else:
            out.append(_rec(tid, "image", tid.split(".")[1], tid + " (interface)",
                            "none", risk, status=PROVIDER_REQUIRED,
                            available=False, installed=False,
                            provider="image backend", tags=("image",),
                            inschema={"type": "object"},
                            needs_install="image backend"))
    for tid in ("chart.generate", "chart.validate", "graph.generate"):
        out.append(_rec(tid, tid.split(".")[0], tid.split(".")[1], tid,
                        "stdlib-svg", READ_ONLY, tags=("chart", "diagram"),
                        inschema={"type": "object"}))
    return out


class VideoAdapter(_Ctx):
    def probe(self):
        import shutil
        ff = bool(shutil.which("ffmpeg"))
        return {"available": ff, "status": AVAILABLE if ff else NOT_INSTALLED,
                "reason": "ffmpeg present" if ff else "ffmpeg not installed",
                "generative": False}

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        if sub in ("generate",):
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    "error": "generative video needs a provider"}
        if sub in ("inspect", "frames"):
            try:
                target = self._resolve(str(arguments.get("path", "")))
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"path refused: {e}"}
            if not target.is_file():
                return {"ok": False, "error": "file not found"}
            return {"ok": True, "path": str(target),
                    "bytes": target.stat().st_size,
                    "note": "container parse needs ffmpeg (absent)"}
        return {"ok": False, "status": NOT_INSTALLED,
                "error": f"video.{sub} needs ffmpeg (not installed)"}


def video_records() -> list[ToolRecord]:
    import shutil
    ff = bool(shutil.which("ffmpeg"))
    out = []
    for tid in ("video.generate", "video.inspect", "video.frames",
                "video.transcode", "video.trim", "video.join",
                "video.resize", "video.subtitle", "video.extract_audio"):
        if tid == "video.generate":
            out.append(_rec(tid, "video", "generate", tid + " (interface)",
                            "none", MUTATING_LOCAL, status=PROVIDER_REQUIRED,
                            available=False, installed=False,
                            provider="video model", tags=("video",),
                            inschema={"type": "object"},
                            needs_install="generative video provider"))
        elif ff:
            out.append(_rec(tid, "video", tid.split(".")[1], tid, "ffmpeg",
                            MUTATING_LOCAL if tid != "video.inspect" else READ_ONLY,
                            tags=("video",), inschema={"type": "object"}))
        else:
            out.append(_rec(tid, "video", tid.split(".")[1], tid + " (interface)",
                            "none", READ_ONLY if tid == "video.inspect" else MUTATING_LOCAL,
                            status=NOT_INSTALLED, available=False,
                            installed=False, tags=("video",),
                            inschema={"type": "object"},
                            needs_install="ffmpeg"))
    return out


class AudioAdapter(_Ctx):
    def probe(self):
        import shutil
        return {"available": True, "status": AVAILABLE,
                "play": bool(shutil.which("powershell")),
                "reason": "wave stdlib + winsound playback; no record/STT backend"}

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        if sub == "inspect":
            try:
                target = self._resolve(str(arguments.get("path", "")))
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"path refused: {e}"}
            try:
                with wave.open(str(target), "rb") as w:
                    return {"ok": True, "channels": w.getnchannels(),
                            "width": w.getsampwidth(),
                            "rate": w.getframerate(),
                            "frames": w.getnframes(),
                            "seconds": round(w.getnframes() / w.getframerate(), 2),
                            "verified": True}
            except (OSError, wave.Error) as e:
                return {"ok": False, "error": f"not a readable WAV: {e}"}
        if sub == "play":
            try:
                target = self._resolve(str(arguments.get("path", "")))
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"path refused: {e}"}
            if not target.is_file():
                return {"ok": False, "error": "file not found"}
            try:
                import winsound
                winsound.PlaySound(str(target),
                                   winsound.SND_FILENAME | winsound.SND_ASYNC)
                return {"ok": True, "playing": str(target)}
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"playback failed: {e}"}
        if sub in ("convert", "trim", "join", "normalize"):
            if not _HAS_AUDIOOP:
                return dict(_AUDIOOP_UNAVAILABLE)
            return self._wav_edit(sub, arguments)
        if sub in ("frequency", "waveform", "spectrum"):
            if not _HAS_AUDIOOP:
                return dict(_AUDIOOP_UNAVAILABLE)
            return self._analyze(sub, arguments)
        if sub in ("record", "transcribe", "generate"):
            return {"ok": False, "status": NOT_INSTALLED,
                    "error": f"audio.{sub} needs a backend (none installed)"}
        return {"ok": False, "error": f"unknown audio subtool: {sub!r}"}

    def _read(self, target):
        with wave.open(str(target), "rb") as w:
            params = w.getparams()
            frames = w.readframes(w.getnframes())
        return params, frames

    def _wav_edit(self, sub, arguments):
        try:
            target = self._resolve(str(arguments.get("path", "")))
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"path refused: {e}"}
        try:
            params, frames = self._read(target)
        except (OSError, wave.Error) as e:
            return {"ok": False, "error": f"unreadable WAV: {e}"}
        nch, width, rate = params.nchannels, params.sampwidth, params.framerate
        if sub == "normalize":
            peak = _audioop.max(frames, width) or 1
            target_peak = int(arguments.get("peak", 30000))
            frames = _audioop.mul(frames, width, target_peak / peak)
        elif sub == "trim":
            start = float(arguments.get("start_s", 0))
            end = arguments.get("end_s", None)
            total = len(frames) // (width * nch)
            end = total if end is None else float(end)
            s0 = int(max(0, start) * rate) * width * nch
            s1 = int(min(total, end) * rate) * width * nch
            frames = frames[s0:s1]
        elif sub == "join":
            others = arguments.get("files", [])
            if not isinstance(others, list) or not others:
                return {"ok": False, "error": "join needs 'files' list"}
            for rel in others:
                try:
                    p2 = self._resolve(str(rel))
                    pr2, fr2 = self._read(p2)
                except Exception as e:  # noqa: BLE001
                    return {"ok": False, "error": f"join file refused: {e}"}
                if (pr2.nchannels, pr2.sampwidth, pr2.framerate) != (nch, width, rate):
                    return {"ok": False, "error": "join needs matching WAV params"}
                frames += fr2
        elif sub == "convert":
            fmt = str(arguments.get("format", "wav")).lower()
            if fmt != "wav":
                return {"ok": False, "status": NOT_INSTALLED,
                        "error": f"convert to {fmt!r} needs a codec backend"}
        dest = str(arguments.get("dest", ""))
        if not dest:
            return {"ok": False, "error": f"audio.{sub} needs 'dest'"}
        try:
            out = self._resolve(dest)
            out.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(out), "wb") as w:
                w.setnchannels(nch)
                w.setsampwidth(width)
                w.setframerate(rate)
                w.writeframes(frames)
        except (OSError, wave.Error) as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "path": str(out), "verified": out.exists()}

    def _analyze(self, sub, arguments):
        try:
            target = self._resolve(str(arguments.get("path", "")))
            params, frames = self._read(target)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"unreadable WAV: {e}"}
        import math
        width = params.sampwidth
        n = min(len(frames) // width, params.framerate * 10)
        samps = [_audioop.getsample(frames, width, i) for i in range(n)]
        if sub == "waveform":
            buckets = 64
            step = max(1, len(samps) // buckets)
            peaks = [max((abs(s) for s in samps[i:i + step]), default=0)
                     for i in range(0, len(samps), step)]
            return {"ok": True, "peaks": peaks[:64]}
        if sub == "frequency":
            # zero-crossing estimate (deterministic, approximate)
            zc = sum(1 for a, b in zip(samps, samps[1:])
                     if (a < 0) != (b < 0))
            dur = len(samps) / params.framerate if params.framerate else 1
            return {"ok": True, "zero_cross_hz": round(zc / 2 / dur, 1),
                    "method": "zero-crossing estimate"}
        if sub == "spectrum":
            N = min(len(samps), 2048)
            mags = []
            for k in range(min(64, N // 2)):
                re = sum(samps[n] * math.cos(2 * math.pi * k * n / N)
                         for n in range(N))
                im = sum(samps[n] * math.sin(2 * math.pi * k * n / N)
                         for n in range(N))
                mags.append(round(math.hypot(re, im) / N, 1))
            return {"ok": True, "bins": mags, "method": "pure-python DFT"}
        return {"ok": False, "error": "unreachable"}


def audio_records() -> list[ToolRecord]:
    out = []
    for tid in ("audio.inspect", "audio.play", "audio.convert", "audio.trim",
                "audio.join", "audio.normalize", "audio.frequency",
                "audio.waveform", "audio.spectrum"):
        risk = READ_ONLY if tid in ("audio.inspect", "audio.frequency",
                                    "audio.waveform", "audio.spectrum") else MUTATING_LOCAL
        out.append(_rec(tid, "audio", tid.split(".")[1], tid, "stdlib-wave",
                        risk, tags=("audio",), inschema={"type": "object"}))
    for tid in ("audio.record", "audio.transcribe", "audio.generate"):
        out.append(_rec(tid, "audio", tid.split(".")[1], tid + " (interface)",
                        "none", MUTATING_LOCAL, status=NOT_INSTALLED,
                        available=False, installed=False,
                        provider="audio backend", tags=("audio",),
                        inschema={"type": "object"},
                        needs_install="record/STT/synth backend"))
    return out


class SpeechAdapter(_Ctx):
    def probe(self):
        import shutil
        ps = bool(shutil.which("powershell"))
        voices = []
        if ps:
            try:
                import subprocess
                p = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "Add-Type -AssemblyName System.Speech; "
                     "(New-Object System.Speech.Synthesis.SpeechSynthesizer)."
                     "GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"],
                    capture_output=True, text=True, timeout=30)
                voices = [v.strip() for v in (p.stdout or "").splitlines()
                          if v.strip()]
            except Exception:  # noqa: BLE001
                voices = []
        return {"available": bool(voices), "status": AVAILABLE if voices
                else NOT_INSTALLED, "voices": voices,
                "reason": "System.Speech voices present" if voices
                else "no TTS backend",
                "stt": False}

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        if sub == "tts":
            return self._tts(arguments)
        if sub in ("stt", "converse"):
            return {"ok": False, "status": NOT_INSTALLED,
                    "error": f"speech.{sub} needs an STT backend (none installed); "
                             "converse is PARTIAL (TTS only)"}
        return {"ok": False, "error": f"unknown speech subtool: {sub!r}"}

    def _tts(self, arguments):
        import subprocess
        import tempfile
        text = str(arguments.get("text", ""))
        if not text.strip():
            return {"ok": False, "error": "tts needs 'text'"}
        if len(text) > 5000:
            return {"ok": False, "error": "text too long (max 5000 chars)"}
        voice = str(arguments.get("voice", ""))
        rate = int(arguments.get("rate", 0) or 0)
        to_file = str(arguments.get("file", ""))
        dest = None
        if to_file:
            try:
                dest = self._resolve(to_file)
                dest.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"path refused: {e}"}
        else:
            dest = Path(tempfile.mkdtemp(prefix="v07_tts_")) / "speech.wav"
        safe_text = text.replace("'", "''")
        ps = (f"Add-Type -AssemblyName System.Speech; "
              f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              + (f"$s.SelectVoice('{voice}'); " if voice else "") +
              f"$s.Rate = {max(-10, min(10, rate))}; "
              f"$s.SetOutputToWaveFile('{dest}'); "
              f"$s.Speak('{safe_text}'); $s.Dispose(); 'TTS_DONE'")
        try:
            p = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               capture_output=True, text=True, timeout=120,
                               shell=False)
        except (OSError, subprocess.TimeoutExpired) as e:
            return {"ok": False, "error": f"tts backend failed: {e}"}
        if "TTS_DONE" not in (p.stdout or "") or not dest.exists() or \
                dest.stat().st_size < 100:
            return {"ok": False,
                    "error": f"tts produced no audio: {(p.stderr or '')[:300]}"}
        return {"ok": True, "path": str(dest), "bytes": dest.stat().st_size,
                "verified": True}


class SttDirectoryAdapter(_Ctx):
    """Backend-free STT directory/status tools (no audio backend needed)."""

    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "STT directory backend present (no audio backend required)"}

    def execute(self, arguments, context=None):
        from multimodal.stt import probe_local
        sub = self.tool_id.split(".", 1)[1]
        if sub == "list_backends":
            found = probe_local()
            return {"ok": True, "backends": [found] if found.get("present") else [],
                    "verified": True}
        if sub == "status":
            found = probe_local()
            return {"ok": True, "status": "AVAILABLE" if found.get("present")
                    else "NOT_INSTALLED", "verified": True}
        if sub == "languages":
            return {"ok": True, "languages": [], "verified": True,
                    "note": "no STT backend installed; languages unknown"}
        return {"ok": False, "error": f"unknown stt subtool: {sub!r}"}


def speech_records() -> list[ToolRecord]:
    return [_rec("speech.tts", "speech", "tts", "text-to-speech (System.Speech)",
                 "system-speech", MUTATING_LOCAL, tags=("speech", "tts"),
                 inschema={"type": "object",
                           "properties": {"text": {"type": "string"},
                                          "voice": {"type": "string"},
                                          "rate": {"type": "integer"},
                                          "file": {"type": "string"}}}),
            _rec("speech.stt", "speech", "stt", "speech-to-text (interface)",
                 "none", READ_ONLY, status=NOT_INSTALLED, available=False,
                 installed=False, provider="STT engine",
                 tags=("speech", "stt"), inschema={"type": "object"},
                 needs_install="Whisper-family or other STT engine"),
            _rec("speech.converse", "speech", "converse",
                 "voice agent loop (PARTIAL: TTS only, no STT)", "partial",
                 MUTATING_LOCAL, status=NOT_INSTALLED, available=False,
                 installed=False, provider="STT engine",
                 tags=("speech", "agent"), inschema={"type": "object"},
                 needs_install="STT backend for full loop"),
            _rec("stt.list_backends", "stt", "list_backends",
                 "STT backend directory (no audio backend needed)",
                 "local-directory", READ_ONLY, tags=("stt", "speech"),
                 inschema={"type": "object"}),
            _rec("stt.status", "stt", "status",
                 "STT backend status (no audio backend needed)",
                 "local-directory", READ_ONLY, tags=("stt", "speech"),
                 inschema={"type": "object"}),
            _rec("stt.languages", "stt", "languages",
                 "STT languages (unknown without backend)",
                 "local-directory", READ_ONLY, tags=("stt", "speech"),
                 inschema={"type": "object"}),
            _rec("stt.transcribe_file", "stt", "transcribe_file",
                 "transcribe audio file (interface)", "none", READ_ONLY,
                 status=NOT_INSTALLED, available=False, installed=False,
                 provider="STT engine (Whisper-compatible plugin slot)",
                 tags=("stt", "speech"),
                 inschema={"type": "object",
                           "properties": {"audio_path": {"type": "string"},
                                          "language": {"type": "string"}}},
                 needs_install="Whisper-compatible STT backend"),
            _rec("stt.start_stream", "stt", "start_stream",
                 "start STT stream (interface)", "none", READ_ONLY,
                 status=NOT_INSTALLED, available=False, installed=False,
                 provider="STT engine (Whisper-compatible plugin slot)",
                 tags=("stt", "speech"), inschema={"type": "object"},
                 needs_install="Whisper-compatible STT backend"),
            _rec("stt.stop_stream", "stt", "stop_stream",
                 "stop STT stream (interface)", "none", READ_ONLY,
                 status=NOT_INSTALLED, available=False, installed=False,
                 provider="STT engine (Whisper-compatible plugin slot)",
                 tags=("stt", "speech"), inschema={"type": "object"},
                 needs_install="Whisper-compatible STT backend")]


class PredictiveAdapter(_Ctx):
    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "local Ollama model backend present"}

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        provider = (context or {}).get("provider")
        if provider is None:
            return {"ok": False, "status": MODEL_REQUIRED,
                    "error": f"{self.tool_id} needs a local model"}
        t0 = __import__("time").monotonic()
        text = str(arguments.get("text", arguments.get("context", "")))
        n = int(arguments.get("n", 3) or 3)
        if not text.strip():
            return {"ok": False, "error": "need text/context"}
        try:
            if sub in ("complete", "next_text"):
                outs = []
                for _ in range(min(max(n, 1), 5)):
                    outs.append(provider.chat(
                        [{"role": "user",
                          "content": f"Continue this text with the most likely next "
                                     f"words (reply with ONLY the continuation):\n{text[-800:]}"}]))
                elapsed = __import__("time").monotonic() - t0
                return {"ok": True, "suggestions": [o[:300] for o in outs],
                        "latency_s": round(elapsed, 2)}
            if sub in ("suggest", "correct", "rewrite"):
                verbs = {"suggest": "Suggest completions for",
                         "correct": "Correct spelling/grammar of",
                         "rewrite": "Rewrite more clearly"}
                out = provider.chat(
                    [{"role": "user",
                      "content": f"{verbs[sub]} (reply with ONLY the result):\n{text[-2000:]}"}])
                return {"ok": True, "result": out[:2000],
                        "latency_s": round(__import__("time").monotonic() - t0, 2)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"predictive failed: {e}"}
        return {"ok": False, "error": f"unknown predictive subtool: {sub!r}"}


def predictive_records() -> list[ToolRecord]:
    out = []
    for tid in ("predictive.complete", "predictive.next_text",
                "predictive.suggest", "predictive.correct",
                "predictive.rewrite"):
        out.append(_rec(tid, "predictive", tid.split(".")[1], tid,
                        "ollama-model", READ_ONLY, requires_model_capability="completion",
                        tags=("predictive", "text"),
                        inschema={"type": "object",
                                  "properties": {"text": {"type": "string"},
                                                 "n": {"type": "integer"}}}))
    for tid in ("autocomplete.text", "autocomplete.code", "autocomplete.file",
                "autocomplete.element", "autocomplete.property",
                "autocomplete.citation", "autocomplete.command",
                "autocomplete.search"):
        out.append(_rec(tid, tid.split(".")[0], tid.split(".")[1], tid,
                        "ollama-model", READ_ONLY,
                        requires_model_capability="completion",
                        tags=("autocomplete",), inschema={"type": "object"}))
    for tid in ("text.summarize", "text.extract", "text.classify",
                "text.translate", "text.correct", "text.rewrite",
                "text.compare", "text.deduplicate", "text.entities",
                "text.keywords", "text.timeline"):
        out.append(_rec(tid, "text", tid.split(".")[1], tid, "ollama-model",
                        READ_ONLY, requires_model_capability="completion",
                        tags=("text",), inschema={"type": "object"}))
    return out


class ComputerAdapter(_Ctx):
    """Reliable-only Windows GUI automation: ctypes user32 + PowerShell
    screenshot + tkinter/clipboard where present. Anything else honest."""

    def probe(self):
        import ctypes
        ok = False
        try:
            ok = bool(ctypes.windll.user32.GetSystemMetrics(0) > 0)
        except Exception:  # noqa: BLE001
            ok = False
        try:
            import tkinter
            tk = True
        except ImportError:
            tk = False
        return {"available": ok, "status": AVAILABLE if ok else UNSUPPORTED_PLATFORM,
                "reason": "user32 screens/mouse/keys; tkinter clipboard"
                if ok else "no GUI session",
                "tkinter": tk}

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        owner = (context or {}).get("profile") == "OWNER_FULL_ACCESS" or \
            (context or {}).get("owner_authorized", False)
        if sub in ("mouse_move", "click", "double_click", "right_click",
                   "drag", "scroll", "key", "type", "hotkey", "close_window",
                   "clipboard_write") and not owner:
            return {"ok": False,
                    "error": f"computer.{sub} needs OWNER_FULL_ACCESS"}
        import ctypes
        u32 = ctypes.windll.user32
        if sub == "screen":
            return {"ok": True, "width": u32.GetSystemMetrics(0),
                    "height": u32.GetSystemMetrics(1), "verified": True}
        if sub == "screenshot":
            return self._screenshot(arguments)
        if sub == "window_list":
            wins: list[str] = []

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def _cb(hwnd, _):
                if u32.IsWindowVisible(hwnd):
                    buf = ctypes.create_unicode_buffer(256)
                    u32.GetWindowTextW(hwnd, buf, 256)
                    if buf.value:
                        wins.append(buf.value[:120])
                return True

            u32.EnumWindows(_cb, 0)
            return {"ok": True, "windows": wins[:100], "count": len(wins)}
        if sub == "window_focus":
            return {"ok": False, "status": NOT_INSTALLED,
                    "error": "window focus by handle needs hwnd plumbing (v0.8+)"}
        if sub in ("launch",):
            import subprocess
            try:
                p = subprocess.Popen(str(arguments.get("command", "")),
                                     shell=True)
                return {"ok": True, "pid": p.pid}
            except OSError as e:
                return {"ok": False, "error": str(e)}
        if sub == "clipboard_read":
            try:
                import tkinter
                r = tkinter.Tk()
                r.withdraw()
                data = r.clipboard_get()
                r.destroy()
                return {"ok": True, "length": len(data),
                        "preview": data[:200]}
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"clipboard unavailable: {e}"}
        if sub == "clipboard_write":
            try:
                import tkinter
                r = tkinter.Tk()
                r.withdraw()
                r.clipboard_clear()
                r.clipboard_append(str(arguments.get("text", ""))[:4000])
                r.update()
                r.destroy()
                return {"ok": True, "written": True}
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"clipboard unavailable: {e}"}
        if sub in ("mouse_move", "click", "double_click", "right_click",
                   "drag", "scroll"):
            x = int(arguments.get("x", -1))
            y = int(arguments.get("y", -1))
            if x >= 0 and y >= 0:
                u32.SetCursorPos(x, y)
            import time as _t
            if sub in ("click", "double_click"):
                for _ in range(2 if sub == "double_click" else 1):
                    u32.mouse_event(0x0002, 0, 0, 0, 0)
                    u32.mouse_event(0x0004, 0, 0, 0, 0)
                    _t.sleep(0.1)
            elif sub == "right_click":
                u32.mouse_event(0x0008, 0, 0, 0, 0)
                u32.mouse_event(0x0010, 0, 0, 0, 0)
            elif sub == "drag":
                x2 = int(arguments.get("x2", x))
                y2 = int(arguments.get("y2", y))
                u32.mouse_event(0x0002, 0, 0, 0, 0)
                u32.SetCursorPos(x2, y2)
                _t.sleep(0.2)
                u32.mouse_event(0x0004, 0, 0, 0, 0)
            elif sub == "scroll":
                u32.mouse_event(0x0800, 0, 0, int(arguments.get("dy", 120)), 0)
            return {"ok": True, "op": sub, "x": x, "y": y}
        if sub in ("key", "type", "hotkey"):
            text = str(arguments.get("text", arguments.get("key", "")))
            if sub == "hotkey":
                return {"ok": False,
                        "error": "hotkey chords need extended plumbing (v0.8+)"}
            if sub == "key" and len(text) > 1 and text.upper() not in (
                    "ENTER", "TAB", "ESC", "ESCAPE", "BACKSPACE", "DELETE",
                    "UP", "DOWN", "LEFT", "RIGHT", "HOME", "END"):
                return {"ok": False, "error": f"unsupported key {text!r}"}
            import time as _t
            if sub == "type":
                for ch in text[:500]:
                    vk = u32.VkKeyScanW(ord(ch)) & 0xFF
                    u32.keybd_event(vk, 0, 0, 0)
                    u32.keybd_event(vk, 0, 2, 0)
                    _t.sleep(0.01)
                return {"ok": True, "typed": len(text[:500])}
            codes = {"ENTER": 0x0D, "TAB": 0x09, "ESC": 0x1B, "ESCAPE": 0x1B,
                     "BACKSPACE": 0x08, "DELETE": 0x2E, "UP": 0x26,
                     "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27, "HOME": 0x24,
                     "END": 0x23}
            vk = codes[text.upper()]
            u32.keybd_event(vk, 0, 0, 0)
            u32.keybd_event(vk, 0, 2, 0)
            return {"ok": True, "key": text}
        if sub == "close_window":
            return {"ok": False,
                    "error": "close_window needs hwnd plumbing (v0.8+)"}
        return {"ok": False, "error": f"unknown computer subtool: {sub!r}"}

    def _screenshot(self, arguments):
        import subprocess
        import tempfile
        dest = str(arguments.get("dest", ""))
        if dest:
            try:
                out = self._resolve(dest)
                out.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"path refused: {e}"}
        else:
            out = Path(tempfile.mkdtemp(prefix="v07_shot_")) / "screen.png"
        psfile = out.parent / "_shot.ps1"
        try:
            psfile.write_text(
                "Add-Type -AssemblyName System.Drawing; "
                "$b = New-Object Drawing.Bitmap("
                "[Windows.Forms.SystemInformation]::VirtualScreen.Width,"
                "[Windows.Forms.SystemInformation]::VirtualScreen.Height); "
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$g = [Drawing.Graphics]::FromImage($b); "
                "$g.CopyFromScreen(0,0,0,0,$b.Size); "
                f"$b.Save('{out}'); 'SHOT_DONE'",
                encoding="utf-8")
            p = subprocess.run(["powershell", "-NoProfile",
                                "-ExecutionPolicy", "Bypass", "-File",
                                str(psfile)], capture_output=True, text=True,
                               timeout=60, shell=False)
        finally:
            try:
                psfile.unlink()
            except OSError:
                pass
        if "SHOT_DONE" not in (p.stdout or "") or not out.exists():
            return {"ok": False,
                    "error": f"screenshot failed: {(p.stderr or '')[:300]}"}
        return {"ok": True, "path": str(out), "bytes": out.stat().st_size,
                "verified": True}


def computer_records() -> list:
    from tools.cat_core import OWNER_ONLY as _OO, _rec as _r
    from tools.registry import MUTATING_LOCAL as _MUT, READ_ONLY as _RO
    out = []
    ro = {"screen", "screenshot", "window_list", "clipboard_read"}
    for tid in ("computer.screen", "computer.screenshot",
                "computer.mouse_move", "computer.click",
                "computer.double_click", "computer.right_click",
                "computer.drag", "computer.scroll", "computer.key",
                "computer.type", "computer.hotkey", "computer.window_list",
                "computer.window_focus", "computer.launch",
                "computer.close_window", "computer.clipboard_read",
                "computer.clipboard_write"):
        sub = tid.split(".")[1]
        risk = _RO if sub in ro else _MUT
        out.append(_r(tid, "computer", sub, tid, "user32/ctypes", risk,
                      profiles=list(_OO), auto=True, tags=("computer", "gui"),
                      inschema={"type": "object"}))
    return out


def ide_records() -> list:
    from tools.cat_core import _rec as _r
    from tools.registry import PROVIDER_REQUIRED as _PR, READ_ONLY as _RO
    out = []
    for tid in ("ide.workspace", "ide.open_file", "ide.search",
                "ide.diagnostics", "ide.project", "ide.terminal",
                "ide.build", "ide.test", "ide.diff"):
        out.append(_r(tid, "ide", tid.split(".")[1], tid + " (interface)",
                      "none", _RO, status=_PR, available=False,
                      installed=False, provider="IDE bridge (unconfigured)",
                      tags=("ide",), inschema={"type": "object"},
                      needs_install="IDE bridge integration"))
    return out

