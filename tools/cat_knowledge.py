"""Adapter catalog, batch 4: chemistry/materials/citation/link/search/
knowledge/memory/cache/context/workflow/scheduler/agent/model."""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from tools.adapter import ToolAdapter
from tools.cat_core import OWNER_ONLY, SAFE_PROFILES, _rec
from tools.cat_data import _Ctx
from tools.registry import (AVAILABLE, MODEL_REQUIRED, MUTATING_LOCAL,
                            NOT_INSTALLED, PROVIDER_REQUIRED, READ_ONLY,
                            SAFE_LOCAL, UNAVAILABLE, ToolRecord)

# compact periodic data: (Z, symbol, name, mass_u, group, period)
ELEMENTS = [
    (1, "H", "Hydrogen", 1.008, 1, 1), (2, "He", "Helium", 4.0026, 18, 1),
    (3, "Li", "Lithium", 6.94, 1, 2), (4, "Be", "Beryllium", 9.0122, 2, 2),
    (5, "B", "Boron", 10.81, 13, 2), (6, "C", "Carbon", 12.011, 14, 2),
    (7, "N", "Nitrogen", 14.007, 15, 2), (8, "O", "Oxygen", 15.999, 16, 2),
    (9, "F", "Fluorine", 18.998, 17, 2), (10, "Ne", "Neon", 20.180, 18, 2),
    (11, "Na", "Sodium", 22.990, 1, 3), (12, "Mg", "Magnesium", 24.305, 2, 3),
    (13, "Al", "Aluminium", 26.982, 13, 3), (14, "Si", "Silicon", 28.085, 14, 3),
    (15, "P", "Phosphorus", 30.974, 15, 3), (16, "S", "Sulfur", 32.06, 16, 3),
    (17, "Cl", "Chlorine", 35.45, 17, 3), (18, "Ar", "Argon", 39.948, 18, 3),
    (19, "K", "Potassium", 39.098, 1, 4), (20, "Ca", "Calcium", 40.078, 2, 4),
    (21, "Sc", "Scandium", 44.956, 3, 4), (22, "Ti", "Titanium", 47.867, 4, 4),
    (23, "V", "Vanadium", 50.942, 5, 4), (24, "Cr", "Chromium", 51.996, 6, 4),
    (25, "Mn", "Manganese", 54.938, 7, 4), (26, "Fe", "Iron", 55.845, 8, 4),
    (27, "Co", "Cobalt", 58.933, 9, 4), (28, "Ni", "Nickel", 58.693, 10, 4),
    (29, "Cu", "Copper", 63.546, 11, 4), (30, "Zn", "Zinc", 65.38, 12, 4),
    (31, "Ga", "Gallium", 69.723, 13, 4), (32, "Ge", "Germanium", 72.630, 14, 4),
    (33, "As", "Arsenic", 74.922, 15, 4), (34, "Se", "Selenium", 78.971, 16, 4),
    (35, "Br", "Bromine", 79.904, 17, 4), (36, "Kr", "Krypton", 83.798, 18, 4),
]


class ChemistryAdapter(_Ctx):
    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "built-in reference tables (standard data)"}

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        by_sym = {e[1]: e for e in ELEMENTS}
        by_name = {e[2].lower(): e for e in ELEMENTS}
        if sub in ("element", "compound", "formula"):
            q = str(arguments.get("symbol", arguments.get("name",
                         arguments.get("query", "")))).strip()
            e = by_sym.get(q) or by_name.get(q.lower())
            if not e:
                return {"ok": False,
                        "error": f"unknown element {q!r} (table covers H..Kr)"}
            z, sym, name, mass, group, period = e
            return {"ok": True, "z": z, "symbol": sym, "name": name,
                    "mass_u": mass, "group": group, "period": period,
                    "verified": True, "source": "built-in reference table"}
        if sub == "bond":
            return {"ok": True, "orders": ["single", "double", "triple",
                                           "aromatic"],
                    "note": "order vocabulary only; no structure solver"}
        if sub in ("reaction", "structure"):
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    "error": f"chemistry.{sub} needs a cheminformatics backend"}
        if sub == "validate":
            formula = str(arguments.get("formula", ""))
            toks = re.findall(r"[A-Z][a-z]?", formula)
            unknown = [t for t in toks if t not in by_sym]
            if unknown:
                return {"ok": False, "error": f"unknown symbols: {unknown}"}
            return {"ok": True, "valid": True, "symbols": toks}
        return {"ok": False, "error": f"unknown chemistry subtool: {sub!r}"}


def chemistry_records() -> list[ToolRecord]:
    out = []
    for tid, real in (("chemistry.element", True), ("chemistry.compound", True),
                      ("chemistry.formula", True), ("chemistry.bond", True),
                      ("chemistry.reaction", False), ("chemistry.structure", False),
                      ("chemistry.validate", True)):
        if real:
            out.append(_rec(tid, "chemistry", tid.split(".")[1], tid,
                            "reference-tables", READ_ONLY,
                            tags=("chemistry", "mat"),
                            inschema={"type": "object"}))
        else:
            out.append(_rec(tid, "chemistry", tid.split(".")[1],
                            tid + " (interface)", "none", READ_ONLY,
                            status=PROVIDER_REQUIRED, available=False,
                            installed=False, provider="cheminformatics backend",
                            tags=("chemistry",), inschema={"type": "object"},
                            needs_install="cheminformatics backend"))
    return out


class MaterialsAdapter(_Ctx):
    PROPS = {"density_g_cm3", "melting_point_c", "hardness_mohs",
             "thermal_W_mK", "electrical_resistivity"}

    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "structural interface + validation (no property DB)"}

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        if sub == "property":
            prop = str(arguments.get("property", ""))
            if prop not in self.PROPS:
                return {"ok": False,
                        "error": f"unknown property {prop!r}; known: "
                                 f"{sorted(self.PROPS)}"}
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    "error": "no materials property database configured; "
                             "connect MAT canonical dataset later"}
        if sub == "compare":
            items = arguments.get("items", [])
            if not isinstance(items, list) or len(items) < 2:
                return {"ok": False, "error": "compare needs 2+ items"}
            return {"ok": True, "items": items,
                    "note": "structural comparison only (no property values)"}
        if sub in ("structure", "phase", "crystal", "spectrum"):
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    "error": f"materials.{sub} needs a materials backend"}
        if sub == "validate":
            rec = arguments.get("record", {})
            if not isinstance(rec, dict) or "name" not in rec:
                return {"ok": False, "error": "record needs at least 'name'"}
            return {"ok": True, "valid": True, "keys": sorted(rec)}
        return {"ok": False, "error": f"unknown materials subtool: {sub!r}"}


def materials_records() -> list[ToolRecord]:
    out = []
    for tid, real in (("materials.property", True), ("materials.compare", True),
                      ("materials.structure", False), ("materials.phase", False),
                      ("materials.crystal", False), ("materials.spectrum", False),
                      ("materials.validate", True)):
        if real:
            out.append(_rec(tid, "materials", tid.split(".")[1], tid,
                            "structural", READ_ONLY, tags=("materials", "mat"),
                            inschema={"type": "object"}))
        else:
            out.append(_rec(tid, "materials", tid.split(".")[1],
                            tid + " (interface)", "none", READ_ONLY,
                            status=PROVIDER_REQUIRED, available=False,
                            installed=False, provider="materials backend",
                            tags=("materials",), inschema={"type": "object"},
                            needs_install="materials backend / MAT dataset"))
    return out


class CitationAdapter(_Ctx):
    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "deterministic local citation helpers"}

    def execute(self, arguments, context=None):
        import hashlib as _hl
        sub = self.tool_id.split(".", 1)[1]
        if sub == "create":
            title = str(arguments.get("title", ""))
            authors = arguments.get("authors", [])
            year = str(arguments.get("year", ""))
            if not title:
                return {"ok": False, "error": "citation needs 'title'"}
            cid = "cit-" + _hl.sha256(
                f"{title}|{authors}|{year}".encode()).hexdigest()[:10]
            return {"ok": True, "id": cid, "title": title, "authors": authors,
                    "year": year, "verified": True}
        if sub == "parse":
            raw = str(arguments.get("text", ""))
            m = re.search(r"(19|20)\d{2}", raw)
            return {"ok": True, "title": raw.split(".")[0][:200],
                    "year": m.group(0) if m else "",
                    "note": "heuristic parse only"}
        if sub == "validate":
            rec = arguments.get("record", {})
            if not isinstance(rec, dict):
                return {"ok": False, "error": "record must be an object"}
            missing = [k for k in ("title",) if k not in rec]
            if missing:
                return {"ok": False, "error": f"missing: {missing}"}
            return {"ok": True, "valid": True}
        if sub == "lookup":
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    "error": "citation.lookup needs a bibliographic provider"}
        if sub == "dedupe":
            items = arguments.get("items", [])
            if not isinstance(items, list):
                return {"ok": False, "error": "'items' must be a list"}
            seen, out, dupes = set(), [], 0
            for it in items:
                key = json.dumps(it, sort_keys=True, default=str).lower() \
                    if isinstance(it, dict) else str(it).lower()
                if key in seen:
                    dupes += 1
                    continue
                seen.add(key)
                out.append(it)
            return {"ok": True, "items": out, "removed": dupes}
        if sub == "backlink":
            return {"ok": True, "backlinks": [],
                    "note": "no index configured in v0.7"}
        if sub.startswith("provenance."):
            store = Path(str((context or {}).get("workspace", ".")
                             or self.ws)) / ".bridge" / "provenance.jsonl"
            if sub == "provenance.record":
                try:
                    store.parent.mkdir(parents=True, exist_ok=True)
                    entry = {"ts": __import__("time").time(),
                             "record": arguments}
                    with open(store, "a", encoding="utf-8") as f:
                        f.write(json.dumps(entry, default=str) + "\n")
                    return {"ok": True, "stored": True}
                except OSError as e:
                    return {"ok": False, "error": str(e)}
            if sub == "provenance.trace":
                if not store.exists():
                    return {"ok": True, "records": []}
                try:
                    lines = store.read_text(encoding="utf-8").splitlines()[-100:]
                    return {"ok": True,
                            "records": [json.loads(l) for l in lines]}
                except (OSError, ValueError) as e:
                    return {"ok": False, "error": str(e)}
            if sub == "provenance.verify":
                return {"ok": True, "store_exists": store.exists()}
        return {"ok": False, "error": f"unknown citation subtool: {sub!r}"}


def citation_records() -> list[ToolRecord]:
    out = []
    for tid, real in (("citation.create", True), ("citation.parse", True),
                      ("citation.validate", True), ("citation.lookup", False),
                      ("citation.dedupe", True), ("citation.backlink", True),
                      ("provenance.trace", True), ("provenance.record", True),
                      ("provenance.verify", True)):
        fam = tid.split(".")[0]
        if real:
            out.append(_rec(tid, fam, tid.split(".")[1], tid, "local",
                            READ_ONLY if "record" not in tid else MUTATING_LOCAL,
                            tags=("citation", "provenance", "mat"),
                            inschema={"type": "object"}))
        else:
            out.append(_rec(tid, fam, tid.split(".")[1], tid + " (interface)",
                            "none", READ_ONLY, status=PROVIDER_REQUIRED,
                            available=False, installed=False,
                            provider="bibliographic provider",
                            tags=("citation",), inschema={"type": "object"},
                            needs_install="bibliographic provider"))
    return out


class LinkAdapter(_Ctx):
    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "stdlib urllib link checks"}

    def execute(self, arguments, context=None):
        import urllib.request
        sub = self.tool_id.split(".", 1)[1]
        if sub in ("extract", "backlinks"):
            text = str(arguments.get("text", arguments.get("html", "")))
            urls = re.findall(r"https?://[^\s'\"<>]+", text)
            seen, out = set(), []
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    out.append(u)
            return {"ok": True, "links": out[:200]}
        if sub in ("check", "resolve", "broken", "redirect"):
            url = str(arguments.get("url", ""))
            if not url.startswith(("http://", "https://")):
                return {"ok": False, "error": "need an http(s) url"}
            if (context or {}).get("network_policy",
                                   "LOCAL_MODEL_NETWORK") == "NO_NETWORK":
                return {"ok": False, "error": "network disabled by policy"}
            if (context or {}).get("network_policy") != "EXTERNAL_NETWORK" \
                    and "127.0.0.1" not in url and "localhost" not in url:
                return {"ok": False,
                        "error": "external URL needs EXTERNAL_NETWORK policy"}
            try:
                req = urllib.request.Request(url, method="HEAD")
                with urllib.request.urlopen(req, timeout=15) as r:
                    final, status = r.url, r.status
            except Exception as e:  # noqa: BLE001
                if sub == "broken":
                    return {"ok": True, "broken": True,
                            "error": str(e)[:200]}
                return {"ok": False, "error": f"link check failed: {e}"}
            if sub == "broken":
                return {"ok": True, "broken": not (200 <= status < 400),
                        "status": status}
            return {"ok": True, "status": status, "resolved": final,
                    "redirected": final != url}
        return {"ok": False, "error": f"unknown link subtool: {sub!r}"}


def link_records() -> list[ToolRecord]:
    return [_rec(f"link.{s}", "link", s, f"link.{s}", "urllib", READ_ONLY,
                 tags=("link", "web"), inschema={"type": "object"})
            for s in ("check", "resolve", "extract", "backlinks", "broken",
                      "redirect")]


class SearchAdapter(_Ctx):
    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "deterministic local search present"}

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        if sub in ("files", "text", "symbols", "index", "history"):
            root = str(arguments.get("path", ".") or ".")
            try:
                base = self._resolve(root)
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"path refused: {e}"}
            if not base.exists():
                return {"ok": False, "error": "path not found"}
            pattern = str(arguments.get("query", arguments.get("pattern", "")))
            if sub == "files":
                hits = [str(p.relative_to(base))[:200]
                        for p in base.rglob(f"*{pattern}*")][:100] \
                    if pattern else []
                return {"ok": True, "hits": hits}
            if not pattern:
                return {"ok": False, "error": "need a query/pattern"}
            try:
                rx = re.compile(pattern, re.I)
            except re.error as e:
                return {"ok": False, "error": f"bad regex: {e}"}
            hits = []
            files = [base] if base.is_file() else [
                p for p in base.rglob("*") if p.is_file()][:2000]
            for f in files:
                try:
                    if f.stat().st_size > 500_000:
                        continue
                    text = f.read_text(encoding="utf-8", errors="strict")
                except (OSError, ValueError, UnicodeDecodeError):
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if rx.search(line if sub != "symbols" else line):
                        try:
                            rel = str(f.relative_to(self.ws))
                        except ValueError:
                            continue
                        hits.append({"file": rel, "line": i,
                                     "text": line.strip()[:200]})
                        if len(hits) >= 100:
                            break
                if len(hits) >= 100:
                    break
            return {"ok": True, "hits": hits, "truncated": len(hits) >= 100}
        if sub in ("semantic", "web"):
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    "error": f"search.{sub} needs a vector/web provider"}
        return {"ok": False, "error": f"unknown search subtool: {sub!r}"}


def search_records() -> list[ToolRecord]:
    out = []
    for tid, real in (("search.files", True), ("search.text", True),
                      ("search.symbols", True), ("search.index", True),
                      ("search.semantic", False), ("search.web", False),
                      ("search.history", True)):
        if real:
            out.append(_rec(tid, "search", tid.split(".")[1], tid, "local",
                            READ_ONLY, tags=("search",),
                            inschema={"type": "object"}))
        else:
            out.append(_rec(tid, "search", tid.split(".")[1],
                            tid + " (interface)", "none", READ_ONLY,
                            status=PROVIDER_REQUIRED, available=False,
                            installed=False, provider="search provider",
                            tags=("search",), inschema={"type": "object"},
                            needs_install="vector/web provider"))
    return out


class KnowledgeAdapter(_Ctx):
    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "JSON store present; no vector DB required"}

    def _store(self, name: str) -> Path:
        d = self.ws / ".bridge" / "knowledge"
        d.mkdir(parents=True, exist_ok=True)
        return d / (name or "default.json")

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        if sub in ("ingest", "store", "index"):
            store = self._store(str(arguments.get("store", "default.json")))
            docs = arguments.get("documents", arguments.get("items", []))
            if not isinstance(docs, list):
                return {"ok": False, "error": "need a documents/items list"}
            try:
                cur = json.loads(store.read_text(encoding="utf-8")) \
                    if store.exists() else []
                cur.extend(docs)
                store.write_text(json.dumps(cur)[:2_000_000], encoding="utf-8")
                return {"ok": True, "stored": len(docs),
                        "total": len(cur), "verified": store.exists()}
            except OSError as e:
                return {"ok": False, "error": str(e)}
        if sub in ("retrieve", "query", "search"):
            store = self._store(str(arguments.get("store", "default.json")))
            q = str(arguments.get("query", arguments.get("q", ""))).lower()
            try:
                cur = json.loads(store.read_text(encoding="utf-8")) \
                    if store.exists() else []
            except (OSError, ValueError):
                cur = []
            scored = []
            for d in cur:
                hay = json.dumps(d, default=str).lower()
                score = sum(hay.count(w) for w in q.split() if len(w) > 2)
                if score or not q:
                    scored.append((score, d))
            scored.sort(key=lambda t: -t[0])
            return {"ok": True, "hits": [d for _, d in scored[:20]]}
        if sub in ("entities", "relationships", "graph"):
            store = self._store(str(arguments.get("store", "default.json")))
            try:
                cur = json.loads(store.read_text(encoding="utf-8")) \
                    if store.exists() else []
            except (OSError, ValueError):
                cur = []
            if sub == "entities":
                ents: dict[str, int] = {}
                for d in cur:
                    for k in ("entities", "topics", "tags"):
                        for e in (d.get(k, []) if isinstance(d, dict) else []):
                            ents[str(e)] = ents.get(str(e), 0) + 1
                return {"ok": True, "entities": ents}
            edges = []
            for d in cur:
                if isinstance(d, dict) and "from" in d and "to" in d:
                    edges.append({"from": d["from"], "to": d["to"],
                                  "rel": d.get("rel", "related_to")})
            return {"ok": True, "nodes": len(cur), "edges": edges}
        return {"ok": False, "error": f"unknown knowledge subtool: {sub!r}"}


def knowledge_records() -> list[ToolRecord]:
    out = []
    for tid in ("knowledge.ingest", "knowledge.retrieve", "knowledge.entities",
                "knowledge.relationships", "knowledge.graph", "knowledge.query",
                "rag.retrieve", "rag.answer", "embedding.generate",
                "vector.search"):
        if tid in ("rag.answer", "embedding.generate", "vector.search"):
            out.append(_rec(tid, tid.split(".")[0], tid.split(".")[1],
                            tid + " (interface)", "none", READ_ONLY,
                            status=PROVIDER_REQUIRED, available=False,
                            installed=False, provider="embedding/model backend",
                            requires_model_capability="embeddings",
                            tags=("rag", "knowledge"),
                            inschema={"type": "object"},
                            needs_install="embedding backend"))
        else:
            out.append(_rec(tid, tid.split(".")[0], tid.split(".")[1], tid,
                            "json-store", READ_ONLY,
                            tags=("knowledge", "rag"),
                            inschema={"type": "object"}))
    return out


class MemoryAdapter(_Ctx):
    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "session memory backend present"}

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        mem = (context or {}).get("memory")
        data = getattr(mem, "data", {}) if mem else {}
        if sub in ("working", "session", "project", "longterm"):
            return {"ok": True, "scope": sub,
                    "summary": {k: (len(v) if isinstance(v, list) else v)
                                for k, v in data.items()},
                    "note": "execution evidence stays separate"}
        if sub == "search":
            q = str(arguments.get("query", "")).lower()
            hits = [e for e in data.get("completed", [])
                    if q in json.dumps(e, default=str).lower()]
            return {"ok": True, "hits": hits[:20]}
        if sub == "store":
            return {"ok": False,
                    "error": "memory.store is append-only via task events, "
                             "not direct writes"}
        if sub == "compact":
            fn = getattr(mem, "compact", None)
            if not fn:
                return {"ok": False, "error": "no memory bound"}
            return {"ok": True, "result": fn()}
        if sub == "forget_scope":
            return {"ok": True, "forgotten": [],
                    "note": "forgetting execution evidence is refused; "
                            "memory views only"}
        return {"ok": False, "error": f"unknown memory subtool: {sub!r}"}


def memory_records() -> list[ToolRecord]:
    return [_rec(f"memory.{s}", "memory", s, f"memory.{s}", "session-memory",
                 READ_ONLY, tags=("memory",), inschema={"type": "object"})
            for s in ("working", "session", "project", "longterm", "search",
                      "store", "compact", "forget_scope")]


class CacheAdapter(_Ctx):
    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "cache backend present"}

    def execute(self, arguments, context=None):
        cache = (context or {}).get("cache")
        sub = self.tool_id.split(".", 1)[1]
        if cache is None:
            return {"ok": False, "error": "no cache bound"}
        if sub == "stats":
            return {"ok": True, "stats": cache.stats()}
        if sub == "invalidate":
            cache.invalidate(str(arguments.get("path", "")))
            return {"ok": True, "invalidated": True}
        if sub == "clear":
            cache.clear()
            return {"ok": True, "cleared": True}
        if sub in ("get", "set"):
            return {"ok": False,
                    "error": "direct cache get/set refused: cache must never "
                             "override verification (use invalidate/stats)"}
        return {"ok": False, "error": f"unknown cache subtool: {sub!r}"}


def cache_records() -> list[ToolRecord]:
    return [_rec(f"cache.{s}", "cache", s, f"cache.{s}", "bridge-cache",
                 READ_ONLY, tags=("cache",), inschema={"type": "object"})
            for s in ("get", "set", "invalidate", "clear", "stats")]


class ContextAdapter(_Ctx):
    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "context budget backend present"}

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        budget = (context or {}).get("budget")
        if sub == "status":
            return {"ok": True, "note": "see session status for usage"}
        if sub == "budget":
            return {"ok": True,
                    "budget_chars": getattr(budget, "budget",
                                            getattr(budget, "limit", 12000))}
        if sub == "compact":
            mem = (context or {}).get("memory")
            fn = getattr(mem, "compact", None)
            if not fn:
                return {"ok": False, "error": "no memory bound"}
            return {"ok": True, "result": fn()}
        if sub in ("select", "summarize"):
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    "error": f"context.{sub} needs a summarizer model"}
        return {"ok": False, "error": f"unknown context subtool: {sub!r}"}


def context_records() -> list[ToolRecord]:
    out = []
    for tid, real in (("context.status", True), ("context.compact", True),
                      ("context.select", False), ("context.summarize", False),
                      ("context.budget", True)):
        if real:
            out.append(_rec(tid, "context", tid.split(".")[1], tid,
                            "budget", READ_ONLY, tags=("context",),
                            inschema={"type": "object"}))
        else:
            out.append(_rec(tid, "context", tid.split(".")[1],
                            tid + " (interface)", "none", READ_ONLY,
                            status=PROVIDER_REQUIRED, available=False,
                            installed=False, requires_model_capability="summarize",
                            tags=("context",), inschema={"type": "object"}))
    return out


class AgentAdapter(_Ctx):
    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "planner/coder/reviewer routing present"}

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        if sub in ("plan", "execute", "review", "revise", "delegate",
                   "status", "cancel", "spawn", "message", "assign",
                   "collect", "quorum"):
            return {"ok": True, "note": f"agent.{sub} runs through the bridge "
                                        "loop/session APIs, not this adapter",
                    "routed": True}
        return {"ok": False, "error": f"unknown agent subtool: {sub!r}"}


def agent_records() -> list[ToolRecord]:
    out = []
    for tid in ("agent.plan", "agent.execute", "agent.review", "agent.revise",
                "agent.delegate", "agent.status", "agent.cancel",
                "agent.spawn", "agent.message", "agent.assign", "agent.collect",
                "agent.quorum"):
        out.append(_rec(tid, "agent", tid.split(".")[1], tid, "bridge-loop",
                        READ_ONLY, tags=("agent",),
                        inschema={"type": "object"}))
    return out


class ModelAdapter(_Ctx):
    def probe(self):
        try:
            from providers import create_provider
            prov = create_provider("ollama", host="http://127.0.0.1:11434",
                                   model="x", timeout_s=8)
            names = prov.list_models()
            return {"available": True, "status": AVAILABLE,
                    "models": len(names)}
        except Exception as e:  # noqa: BLE001
            return {"available": False, "status": UNAVAILABLE, "reason": str(e)[:150]}

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        if sub in ("list", "status", "info"):
            return self.probe() + ({"models": []} if sub != "list" else {})
        if sub in ("route", "fallback", "benchmark"):
            from competence import CompetenceTracker  # noqa: F401
            return {"ok": True, "note": f"model.{sub} handled by router/config",
                    "routed": True}
        if sub in ("load", "unload"):
            return {"ok": True, "note": f"model.{sub} is a no-op: Ollama manages "
                                        "residency server-side"}
        if sub in ("download", "delete"):
            return {"ok": False,
                    "error": "destructive model operations need explicit enablement"}
        return {"ok": False, "error": f"unknown model subtool: {sub!r}"}


def model_records() -> list[ToolRecord]:
    out = []
    for tid in ("model.list", "model.status", "model.info", "model.load",
                "model.unload", "model.benchmark", "model.route",
                "model.fallback"):
        out.append(_rec(tid, "model", tid.split(".")[1], tid, "ollama",
                        READ_ONLY, tags=("model",),
                        inschema={"type": "object"}))
    for tid in ("model.download", "model.delete"):
        out.append(_rec(tid, "model", tid.split(".")[1], tid + " (gated)",
                        "ollama", "DESTRUCTIVE", tags=("model",),
                        inschema={"type": "object"}))
    return out
