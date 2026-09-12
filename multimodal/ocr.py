"""Windows OCR backend (v0.8, Part 5). OS-native, no downloads.

Uses Windows.Media.Ocr (WinRT) via a PowerShell bridge: presence-checked,
bounded timeouts, image/reference input only. Returns text, lines, words
with bounding boxes, language, and source reference. WinRT exposes NO
per-word confidence — reported honestly as not supplied.
"""
from __future__ import annotations

import subprocess
from typing import Any

_BRIDGE_PREAMBLE = r"""
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$OcrEngine = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$StorageFile = [Windows.Storage.StorageFile, Windows.Foundation, ContentType=WindowsRuntime]
$FileAccess = [Windows.Storage.FileAccessMode, Windows.Foundation, ContentType=WindowsRuntime]
$BitmapDecoder = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType=WindowsRuntime]
$SoftwareBitmap = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType=WindowsRuntime]
$OcrResult = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType=WindowsRuntime]
$IRandomAccessStream = [Windows.Storage.Streams.IRandomAccessStream, Windows.Foundation, ContentType=WindowsRuntime]
function Await($task, $resultType) {
    $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition })[0]
    $t = $asTask.MakeGenericMethod($resultType).Invoke($null, @($task))
    $t.GetAwaiter().GetResult()
}
"""


def is_available(timeout_s: int = 30) -> dict[str, Any]:
    """Presence check: engine creatable from user profile languages?"""
    script = _BRIDGE_PREAMBLE + r"""
try {
    $engine = $OcrEngine::TryCreateFromUserProfileLanguages()
    if ($null -eq $engine) { "ENGINE_NULL" } else { "ENGINE:" + $engine.RecognizerLanguage.LanguageTag }
} catch { "ERROR:" + $_.Exception.Message }
"""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                           capture_output=True, text=True, timeout=timeout_s)
        out = (r.stdout or "").strip().splitlines()
        line = out[-1].strip() if out else ""
        if line.startswith("ENGINE:"):
            return {"present": True, "backend": "windows-ocr",
                    "language": line.split(":", 1)[1]}
        return {"present": False, "backend": "none",
                "status": "NOT_INSTALLED", "reason": line or "unknown"}
    except Exception as e:  # noqa: BLE001
        return {"present": False, "backend": "none",
                "status": "NOT_INSTALLED", "reason": str(e)[:200]}


def _quote_path(path: str) -> str:
    if not isinstance(path, str) or not path or len(path) > 260:
        raise ValueError("bad image path")
    return "'" + path.replace("'", "''") + "'"


def recognize(image_path: str, timeout_s: int = 120) -> dict[str, Any]:
    """OCR one image file. Returns canonical contract dict."""
    script = (
        _BRIDGE_PREAMBLE
        + "$ImagePath = " + _quote_path(image_path) + "\n"
        + "try {\n"
        + "    $engine = $OcrEngine::TryCreateFromUserProfileLanguages()\n"
        + '    if ($null -eq $engine) { "ENGINE_NULL"; exit 0 }\n'
        + "    $file = Await ($StorageFile::GetFileFromPathAsync($ImagePath)) $StorageFile\n"
        + "    $stream = Await ($file.OpenAsync($FileAccess::Read)) $IRandomAccessStream\n"
        + "    $decoder = Await ($BitmapDecoder::CreateAsync($stream)) $BitmapDecoder\n"
        + "    $bmp = Await ($decoder.GetSoftwareBitmapAsync()) $SoftwareBitmap\n"
        + "    $result = Await ($engine.RecognizeAsync($bmp)) $OcrResult\n"
        + "    $words = @()\n"
        + "    foreach ($ln in $result.Lines) {\n"
        + "        foreach ($w in $ln.Words) {\n"
        + "            $r = $w.BoundingRect\n"
        + '            $words += @{"text"=$w.Text; "box"=@($r.X, $r.Y, $r.Width, $r.Height)}\n'
        + "        }\n"
        + "    }\n"
        + "    $lines = @()\n"
        + "    foreach ($ln in $result.Lines) { $lines += $ln.Text }\n"
        + '    "PAYLOAD:" + (@{"text"=$result.Text; "angle"=$result.TextAngle;\n'
        + '        "language"=$engine.RecognizerLanguage.LanguageTag;\n'
        + '        "lines"=$lines; "words"=$words;\n'
        + '        "confidence"="not supplied by Windows OCR backend"} | ConvertTo-Json -Compress -Depth 5)\n'
        + '} catch { "OCR_FAILED: " + $_.Exception.Message }\n'
    )
    import json
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=timeout_s)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status": "NOT_INSTALLED", "error": str(e)[:200]}
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("PAYLOAD:"):
            payload = json.loads(line[len("PAYLOAD:"):])
            return {"ok": True, "status": "AVAILABLE",
                    "source_artifact": image_path,
                    "provenance": "windows-ocr (WinRT, OS-native, local)",
                    **payload}
        if line in ("ENGINE_NULL",) or line.startswith("OCR_FAILED"):
            return {"ok": False, "status": "NOT_INSTALLED", "error": line[:200]}
    return {"ok": False, "status": "NOT_INSTALLED",
            "error": ((r.stderr or "").strip()[:200] or "no OCR output")}


def render_fixture_text(text: str, dest_path: str, timeout_s: int = 60) -> dict[str, Any]:
    """Render deterministic fixture PNG with known text (System.Drawing)."""
    if not isinstance(text, str) or not text or len(text) > 120:
        return {"ok": False, "error": "bad fixture text"}
    script = (
        "$Text = '" + text.replace("'", "''") + "'\n"
        "$Dest = " + _quote_path(dest_path) + "\n"
        "Add-Type -AssemblyName System.Drawing\n"
        "$bmp = New-Object System.Drawing.Bitmap(600, 120)\n"
        "$g = [System.Drawing.Graphics]::FromImage($bmp)\n"
        "$g.Clear([System.Drawing.Color]::White)\n"
        '$font = New-Object System.Drawing.Font("Arial", 30)\n'
        "$g.DrawString($Text, $font, "
        "[System.Drawing.Brushes]::Black, 10, 30)\n"
        "$g.Dispose()\n"
        "$bmp.Save($Dest, [System.Drawing.Imaging.ImageFormat]::Png)\n"
        '"FIXTURE_SAVED:" + $Dest')
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=timeout_s)
        import os
        if os.path.exists(dest_path):
            return {"ok": True, "path": dest_path,
                    "bytes": os.path.getsize(dest_path)}
        return {"ok": False, "error": ((r.stdout or "") + (r.stderr or "")).strip()[:200]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}
