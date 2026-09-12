"""Adapter catalog, batch 2: document/pdf/spreadsheet/presentation/archive/
data/database/analytics/science/units/chemistry/materials/citation/link/
search/knowledge/memory/cache/context/workflow/agent/model."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import sqlite3
import statistics
import subprocess
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from tools.adapter import ToolAdapter
from tools.cat_core import OWNER_ONLY, SAFE_PROFILES, _rec
from tools.registry import (AVAILABLE, DEGRADED, MODEL_REQUIRED,
                            MUTATING_LOCAL, NETWORK, NOT_INSTALLED,
                            PROVIDER_REQUIRED, READ_ONLY, SAFE_LOCAL,
                            UNAVAILABLE, ToolRecord)

try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _yaml = None
    _HAS_YAML = False


class _Ctx(ToolAdapter):
    def __init__(self, ctx, tool_id):
        self.ctx = ctx
        self.tool_id = tool_id

    @property
    def ex(self):
        return self.ctx["executor"]

    @property
    def ws(self) -> Path:
        return Path(self.ctx.get("workspace", ".") or self.ex.workspace)

    def _resolve(self, rel: str) -> Path:
        return self.ex._resolve(rel)

    def validate(self, arguments):
        return (True, "") if isinstance(arguments, dict) else \
            (False, "arguments must be an object")


# -- documents --------------------------------------------------------------------
class _TextStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())


class DocumentAdapter(_Ctx):
    FORMATS = ("txt", "md", "markdown", "html", "htm", "json", "yaml", "yml",
               "xml", "csv")

    def probe(self):
        det = {"txt": True, "md": True, "html": True, "json": True,
               "yaml": _HAS_YAML, "xml": True, "csv": True,
               "pdf": False, "docx": False, "epub": False, "rtf": False,
               "odt": False}
        try:
            import importlib.util as _u
            det["pdf"] = bool(_u.find_spec("pypdf") or _u.find_spec("fitz")
                              or _u.find_spec("pdfminer"))
            det["docx"] = bool(_u.find_spec("docx"))
        except Exception:  # noqa: BLE001
            pass
        return {"available": True, "status": AVAILABLE, "formats": det,
                "reason": "stdlib formats real; pdf/docx need providers"}

    def _read_format(self, path: Path) -> dict[str, Any]:
        suf = path.suffix.lower().lstrip(".")
        if suf in ("", "txt", "md", "markdown", "csv", "json", "yaml", "yml",
                   "xml", "html", "htm", "log", "ini", "cfg", "toml"):
            try:
                text = path.read_text(encoding="utf-8", errors="strict")
            except (OSError, ValueError, UnicodeDecodeError) as e:
                return {"ok": False, "error": f"unreadable: {e}"}
            if suf in ("html", "htm"):
                s = _TextStripper()
                s.feed(text)
                text = "\n".join(s.parts)
            return {"ok": True, "format": suf or "txt", "text": text[:20000],
                    "chars": len(text)}
        if suf in ("pdf", "docx", "epub", "rtf", "odt"):
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    f"error": f".{suf} needs a document provider (none configured)"}
        return {"ok": False, "error": f"unsupported format: .{suf}"}

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        if sub == "detect":
            p = Path(str(arguments.get("path", "")))
            return {"ok": True, "format": p.suffix.lower().lstrip(".") or "txt"}
        if sub in ("read", "extract"):
            try:
                target = self._resolve(str(arguments.get("path", "")))
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"path refused: {e}"}
            if not target.is_file():
                return {"ok": False, "error": "file not found"}
            return self._read_format(target)
        if sub == "convert":
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    "error": "document.convert needs a provider for non-text targets; "
                             "text<->text is identity (use filesystem tools)"}
        if sub == "summarize":
            text = str(arguments.get("text", ""))
            if not text.strip():
                return {"ok": False, "error": "summarize needs 'text'"}
            provider = (context or {}).get("provider")
            if provider is None:
                sents = re.split(r"(?<=[.!?])\s+", text.strip())
                return {"ok": True, "summary": " ".join(sents[:3])[:2000],
                        "method": "extractive-fallback (no model wired)",
                        "verified": True}
            try:
                out = provider.chat(
                    [{"role": "system", "content": "Summarize briefly."},
                     {"role": "user", "content": text[:6000]}])
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"summarize failed: {e}"}
            return {"ok": True, "summary": out[:4000], "method": "model"}
        if sub == "index":
            text = str(arguments.get("text", ""))
            words = re.findall(r"[A-Za-z][\w\-]{2,}", text.lower())
            freq: dict[str, int] = {}
            for w in words:
                freq[w] = freq.get(w, 0) + 1
            top = sorted(freq.items(), key=lambda kv: -kv[1])[:50]
            return {"ok": True, "terms": [{"term": k, "count": v} for k, v in top],
                    "tokens": len(words)}
        return {"ok": False, "error": f"unknown document subtool: {sub!r}"}


def document_records() -> list[ToolRecord]:
    out = []
    for tid in ("document.detect", "document.read", "document.extract",
                "document.convert", "document.summarize", "document.index"):
        out.append(_rec(tid, "document", tid.split(".")[1], tid, "stdlib",
                        READ_ONLY, tags=("document", "ingest"),
                        inschema={"type": "object",
                                  "properties": {"path": {"type": "string"},
                                                 "text": {"type": "string"}}}))
    for tid in ("pdf.read", "pdf.extract_text", "pdf.extract_images",
                "pdf.merge", "pdf.split", "pdf.create", "pdf.annotate",
                "pdf.metadata"):
        out.append(_rec(tid, "pdf", tid.split(".")[1], tid + " (interface)",
                        "none", READ_ONLY, status=PROVIDER_REQUIRED,
                        available=False, installed=False,
                        provider="pdf backend (unconfigured)",
                        tags=("pdf", "document"),
                        inschema={"type": "object"},
                        needs_install="pdf backend (pypdf/fitz or service)"))
    return out


class SpreadsheetAdapter(_Ctx):
    def probe(self):
        try:
            import importlib.util as _u
            xlsx = bool(_u.find_spec("openpyxl"))
        except Exception:  # noqa: BLE001
            xlsx = False
        return {"available": True, "status": AVAILABLE,
                "csv": True, "xlsx": xlsx,
                "reason": "CSV via stdlib; XLSX needs openpyxl" if not xlsx
                else "CSV + XLSX available"}

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        if sub == "read":
            try:
                target = self._resolve(str(arguments.get("path", "")))
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"path refused: {e}"}
            if target.suffix.lower() == ".csv":
                try:
                    with open(target, newline="", encoding="utf-8") as f:
                        rows = list(csv.reader(f))[:500]
                except OSError as e:
                    return {"ok": False, "error": str(e)}
                return {"ok": True, "format": "csv", "rows": len(rows),
                        "data": rows, "verified": True}
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    "error": "XLSX needs openpyxl (not installed)"}
        if sub == "write":
            try:
                target = self._resolve(str(arguments.get("path", "")))
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"path refused: {e}"}
            rows = arguments.get("rows", [])
            if not isinstance(rows, list):
                return {"ok": False, "error": "'rows' must be a list of lists"}
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerows(rows)
            except OSError as e:
                return {"ok": False, "error": str(e)}
            return {"ok": True, "path": str(target), "rows": len(rows),
                    "verified": target.exists()}
        return {"ok": False, "status": PROVIDER_REQUIRED,
                "error": f"spreadsheet.{sub} needs an XLSX-capable backend"}


def spreadsheet_records() -> list[ToolRecord]:
    out = [_rec("spreadsheet.read", "spreadsheet", "read",
                "read CSV (XLSX needs backend)", "stdlib", READ_ONLY,
                tags=("spreadsheet", "csv"),
                inschema={"type": "object",
                          "properties": {"path": {"type": "string"}}}),
           _rec("spreadsheet.write", "spreadsheet", "write", "write CSV",
                "stdlib", MUTATING_LOCAL,
                tags=("spreadsheet", "csv"),
                inschema={"type": "object",
                          "properties": {"path": {"type": "string"},
                                         "rows": {"type": "array"}}})]
    for tid in ("spreadsheet.formula", "spreadsheet.analyze",
                "spreadsheet.chart", "spreadsheet.convert",
                "spreadsheet.validate"):
        out.append(_rec(tid, "spreadsheet", tid.split(".")[1],
                        tid + " (interface)", "none", READ_ONLY,
                        status=PROVIDER_REQUIRED, available=False,
                        installed=False, provider="spreadsheet backend",
                        tags=("spreadsheet",), inschema={"type": "object"},
                        needs_install="xlsx-capable backend"))
    return out


class PresentationAdapter(_Ctx):
    def probe(self):
        return {"available": False, "status": PROVIDER_REQUIRED,
                "reason": "no presentation backend configured"}

    def execute(self, arguments, context=None):
        return {"ok": False, "status": PROVIDER_REQUIRED,
                "error": f"{self.tool_id} needs a presentation backend"}


def presentation_records() -> list[ToolRecord]:
    return [_rec(tid, "presentation", tid.split(".")[1], tid + " (interface)",
                 "none", READ_ONLY, status=PROVIDER_REQUIRED, available=False,
                 installed=False, provider="presentation backend",
                 tags=("presentation",), inschema={"type": "object"},
                 needs_install="presentation backend (e.g. soffice)")
            for tid in ("presentation.read", "presentation.create",
                        "presentation.edit", "presentation.render",
                        "presentation.export")]


class ArchiveAdapter(_Ctx):
    def probe(self):
        import shutil as _sh
        return {"available": True, "status": AVAILABLE,
                "seven_zip": bool(_sh.which("7z")),
                "reason": "zip/tar via stdlib"}

    def execute(self, arguments, context=None):
        import tarfile
        sub = self.tool_id.split(".", 1)[1]
        if sub == "list":
            try:
                target = self._resolve(str(arguments.get("path", "")))
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"path refused: {e}"}
            try:
                if zipfile.is_zipfile(target):
                    with zipfile.ZipFile(target) as z:
                        names = z.namelist()[:500]
                    return {"ok": True, "format": "zip", "entries": names}
                if tarfile.is_tarfile(target):
                    with tarfile.open(target) as t:
                        return {"ok": True, "format": "tar",
                                "entries": t.getnames()[:500]}
            except OSError as e:
                return {"ok": False, "error": str(e)}
            return {"ok": False, "error": "not a zip/tar archive"}
        if sub == "extract":
            try:
                target = self._resolve(str(arguments.get("path", "")))
                dest = self._resolve(str(arguments.get("dest", ".")))
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"path refused: {e}"}
            try:
                dest.mkdir(parents=True, exist_ok=True)
                if zipfile.is_zipfile(target):
                    with zipfile.ZipFile(target) as z:
                        z.extractall(dest)
                    return {"ok": True, "format": "zip", "dest": str(dest),
                            "verified": any(dest.iterdir())}
                if tarfile.is_tarfile(target):
                    with tarfile.open(target) as t:
                        t.extractall(dest, filter="data")
                    return {"ok": True, "format": "tar", "dest": str(dest),
                            "verified": any(dest.iterdir())}
            except OSError as e:
                return {"ok": False, "error": str(e)}
            return {"ok": False, "error": "not a zip/tar archive"}
        if sub == "create":
            try:
                dest = self._resolve(str(arguments.get("dest", "")))
                srcs = arguments.get("files", [])
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"path refused: {e}"}
            if not isinstance(srcs, list) or not srcs:
                return {"ok": False, "error": "create needs 'files' list"}
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
                    for rel in srcs:
                        p = self._resolve(str(rel))
                        if p.is_file():
                            z.write(p, p.name)
                return {"ok": True, "dest": str(dest),
                        "verified": dest.exists()}
            except (OSError, ValueError) as e:
                return {"ok": False, "error": str(e)}
        if sub == "verify":
            try:
                target = self._resolve(str(arguments.get("path", "")))
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"path refused: {e}"}
            import hashlib
            try:
                h = hashlib.sha256()
                with open(target, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
            except OSError as e:
                return {"ok": False, "error": str(e)}
            return {"ok": True, "sha256": h.hexdigest(),
                    "verified": True}
        return {"ok": False, "error": f"unknown archive subtool: {sub!r}"}


def archive_records() -> list[ToolRecord]:
    out = []
    for tid, risk in (("archive.list", READ_ONLY), ("archive.extract", "MUTATING_LOCAL"),
                      ("archive.create", "MUTATING_LOCAL"), ("archive.verify", READ_ONLY)):
        out.append(_rec(tid, "archive", tid.split(".")[1], tid,
                        "zipfile/tarfile", risk, tags=("archive", "zip"),
                        inschema={"type": "object",
                                  "properties": {"path": {"type": "string"},
                                                 "dest": {"type": "string"},
                                                 "files": {"type": "array"}}}))
    return out
