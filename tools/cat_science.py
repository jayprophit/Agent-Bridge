"""Adapter catalog, batch 3: data/database/analytics/science/units/
chemistry/materials/citation/link/search/knowledge/memory/cache/context/
workflow/scheduler/agent/model."""
from __future__ import annotations

import csv
import io
import json
import math
import re
import sqlite3
import statistics
from pathlib import Path
from typing import Any

from tools.adapter import ToolAdapter
from tools.cat_core import OWNER_ONLY, SAFE_PROFILES, _rec
from tools.cat_data import _Ctx
from tools.registry import (AVAILABLE, MODEL_REQUIRED, MUTATING_LOCAL,
                            NETWORK, NOT_INSTALLED, PROVIDER_REQUIRED,
                            READ_ONLY, SAFE_LOCAL, UNAVAILABLE, ToolRecord)


# -- data -----------------------------------------------------------------------
class DataAdapter(_Ctx):
    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "stdlib json/csv/xml (+yaml if installed) present"}

    def execute(self, arguments, context=None):
        import xml.etree.ElementTree as _ET
        sub = self.tool_id.split(".", 1)[1]
        text = str(arguments.get("text", arguments.get("data", "")))
        if sub == "json":
            try:
                obj = json.loads(text) if text else arguments.get("data")
                if isinstance(obj, str):
                    obj = json.loads(obj)
                return {"ok": True, "parsed": True,
                        "pretty": json.dumps(obj, indent=1)[:8000]}
            except (ValueError, TypeError) as e:
                return {"ok": False, "error": f"invalid JSON: {e}"}
        if sub == "yaml":
            try:
                import yaml
            except ImportError:
                return {"ok": False, "status": NOT_INSTALLED,
                        "error": "pyyaml not installed"}
            try:
                return {"ok": True, "data": yaml.safe_load(text)}
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"invalid YAML: {e}"}
        if sub == "xml":
            try:
                root = _ET.fromstring(text)
                return {"ok": True, "root": root.tag,
                        "children": [c.tag for c in root][:50]}
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"invalid XML: {e}"}
        if sub == "csv":
            try:
                rows = list(csv.reader(io.StringIO(text)))[:500]
                return {"ok": True, "rows": len(rows), "data": rows}
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"invalid CSV: {e}"}
        if sub == "convert":
            frm, to = str(arguments.get("from", "")), str(arguments.get("to", ""))
            if frm == "json" and to in ("yaml", "yml"):
                try:
                    import yaml
                except ImportError:
                    return {"ok": False, "status": NOT_INSTALLED,
                            "error": "pyyaml not installed"}
                try:
                    return {"ok": True,
                            "text": yaml.safe_dump(json.loads(text))[:8000]}
                except (ValueError, TypeError) as e:
                    return {"ok": False, "error": str(e)}
            if frm in ("yaml", "yml") and to == "json":
                try:
                    import yaml
                    return {"ok": True, "text": json.dumps(
                        yaml.safe_load(text), indent=1)[:8000]}
                except ImportError:
                    return {"ok": False, "status": NOT_INSTALLED,
                            "error": "pyyaml not installed"}
                except Exception as e:  # noqa: BLE001
                    return {"ok": False, "error": str(e)}
            return {"ok": False,
                    "error": f"unsupported conversion {frm!r}->{to!r}"}
        if sub == "validate":
            schema = arguments.get("schema", {})
            data = arguments.get("data", {})
            if not isinstance(schema, dict):
                return {"ok": False, "error": "schema must be an object"}
            missing = [k for k in schema.get("required", [])
                       if k not in (data if isinstance(data, dict) else {})]
            if missing:
                return {"ok": False, "error": f"missing required: {missing}"}
            return {"ok": True, "valid": True}
        if sub == "schema":
            data = arguments.get("data", {})
            if isinstance(data, dict):
                return {"ok": True, "schema": {
                    "type": "object",
                    "required": sorted(data),
                    "properties": {k: type(v).__name__ for k, v in data.items()}}}
            return {"ok": False, "error": "schema needs an object sample"}
        if sub == "diff":
            a = json.dumps(arguments.get("a", {}), sort_keys=True,
                           indent=1).splitlines()
            b = json.dumps(arguments.get("b", {}), sort_keys=True,
                           indent=1).splitlines()
            import difflib
            return {"ok": True, "diff": "\n".join(
                difflib.unified_diff(a, b, "a", "b"))[:4000]}
        if sub == "merge":
            a, b = arguments.get("a", {}), arguments.get("b", {})
            if not isinstance(a, dict) or not isinstance(b, dict):
                return {"ok": False, "error": "merge needs two objects"}
            merged = dict(a)
            conflicts = [k for k in b if k in merged and merged[k] != b[k]]
            merged.update(b)
            return {"ok": True, "merged": merged, "conflicts": conflicts}
        if sub == "deduplicate":
            items = arguments.get("items", [])
            if not isinstance(items, list):
                return {"ok": False, "error": "'items' must be a list"}
            seen, out, dupes = set(), [], 0
            for it in items:
                key = json.dumps(it, sort_keys=True, default=str)
                if key in seen:
                    dupes += 1
                    continue
                seen.add(key)
                out.append(it)
            return {"ok": True, "items": out, "removed": dupes}
        if sub == "transform":
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    "error": "data.transform needs a mapping spec backend"}
        return {"ok": False, "error": f"unknown data subtool: {sub!r}"}


def data_records() -> list[ToolRecord]:
    return [_rec(f"data.{s}", "data", s, f"data.{s}", "stdlib", READ_ONLY,
                 tags=("data", "json"),
                 inschema={"type": "object"})
            for s in ("json", "yaml", "xml", "csv", "convert", "validate",
                      "schema", "diff", "merge", "deduplicate", "transform")]


class DatabaseAdapter(_Ctx):
    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "sqlite3 stdlib present; others need configuration"}

    def _db(self, arguments) -> sqlite3.Connection:
        path = str(arguments.get("path", ":memory:"))
        if path != ":memory:":
            target = self._resolve(path)
            path = str(target)
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(path)

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        if sub in ("postgres", "mysql", "mongodb"):
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    "error": f"database.{sub} needs a configured server"}
        if sub in ("sqlite", "query", "schema"):
            sql = str(arguments.get("sql", arguments.get("query", "")))
            if not sql.strip():
                return {"ok": False, "error": "database needs 'sql'"}
            lowered = sql.strip().lower()
            if lowered.startswith(("drop database", "shutdown", "vacuum into")):
                return {"ok": False, "error": "refused dangerous statement"}
            try:
                con = self._db(arguments)
                try:
                    cur = con.execute(sql)
                    if lowered.startswith("select") or lowered.startswith(
                            ("pragma", "explain", "with")):
                        rows = cur.fetchall()[:500]
                        cols = [d[0] for d in (cur.description or [])]
                        return {"ok": True, "columns": cols, "rows": rows,
                                "count": len(rows), "verified": True}
                    con.commit()
                    return {"ok": True, "rowcount": cur.rowcount,
                            "verified": True}
                finally:
                    con.close()
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"sqlite failed: {e}"}
        if sub == "migrate":
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    "error": "database.migrate needs a migration backend"}
        if sub in ("backup", "restore"):
            import shutil
            path = str(arguments.get("path", ""))
            dest = str(arguments.get("dest", arguments.get("backup", "")))
            if not path or not dest:
                return {"ok": False, "error": "backup/restore need path+dest"}
            try:
                a, b = self._resolve(path), self._resolve(dest)
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"path refused: {e}"}
            try:
                if sub == "backup":
                    shutil.copy2(a, b)
                    return {"ok": True, "backup": str(b),
                            "verified": b.exists()}
                shutil.copy2(b, a)
                return {"ok": True, "restored": str(a),
                        "verified": a.exists()}
            except OSError as e:
                return {"ok": False, "error": str(e)}
        return {"ok": False, "error": f"unknown database subtool: {sub!r}"}


def database_records() -> list[ToolRecord]:
    out = [_rec("database.sqlite", "database", "sqlite",
                "SQLite via stdlib (query + exec)", "sqlite3", MUTATING_LOCAL,
                tags=("database", "sqlite"),
                inschema={"type": "object",
                          "properties": {"path": {"type": "string"},
                                         "sql": {"type": "string"}}}),
           _rec("database.query", "database", "query", "run a SQL query",
                "sqlite3", READ_ONLY, tags=("database",),
                inschema={"type": "object",
                          "properties": {"path": {"type": "string"},
                                         "sql": {"type": "string"}}}),
           _rec("database.schema", "database", "schema", "inspect schema",
                "sqlite3", READ_ONLY, tags=("database",),
                inschema={"type": "object",
                          "properties": {"path": {"type": "string"},
                                         "sql": {"type": "string"}}}),
           _rec("database.backup", "database", "backup", "file-level backup",
                "shutil", MUTATING_LOCAL, tags=("database", "backup"),
                inschema={"type": "object"}),
           _rec("database.restore", "database", "restore",
                "file-level restore", "shutil", MUTATING_LOCAL,
                tags=("database", "backup"), inschema={"type": "object"})]
    for tid in ("database.postgres", "database.mysql", "database.mongodb",
                "database.migrate"):
        out.append(_rec(tid, "database", tid.split(".")[1], tid + " (interface)",
                        "none", READ_ONLY, status=PROVIDER_REQUIRED,
                        available=False, installed=False,
                        provider="database server (unconfigured)",
                        tags=("database",), inschema={"type": "object"},
                        needs_install="configured database server"))
    return out


class AnalyticsAdapter(_Ctx):
    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "stdlib statistics present"}

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        vals = arguments.get("values", arguments.get("data", []))
        if sub in ("statistics", "aggregate", "filter", "compare", "correlate",
                   "outliers", "timeseries", "report"):
            if not isinstance(vals, list) or not vals:
                return {"ok": False, "error": "'values' must be a non-empty list"}
            try:
                nums = [float(x) for x in vals]
            except (TypeError, ValueError):
                return {"ok": False, "error": "'values' must be numeric"}
            if sub in ("statistics", "report", "aggregate"):
                return {"ok": True, "count": len(nums),
                        "mean": statistics.fmean(nums),
                        "median": statistics.median(nums),
                        "stdev": statistics.pstdev(nums) if len(nums) > 1 else 0.0,
                        "min": min(nums), "max": max(nums),
                        "verified": True}
            if sub == "filter":
                lo = float(arguments.get("min", min(nums)))
                hi = float(arguments.get("max", max(nums)))
                return {"ok": True,
                        "values": [x for x in nums if lo <= x <= hi]}
            if sub == "compare":
                other = [float(x) for x in arguments.get("other", [])]
                if not other:
                    return {"ok": False, "error": "compare needs 'other'"}
                return {"ok": True,
                        "mean_delta": statistics.fmean(nums) - statistics.fmean(other)}
            if sub == "correlate":
                other = [float(x) for x in arguments.get("other", [])]
                if len(other) != len(nums) or len(nums) < 2:
                    return {"ok": False,
                            "error": "correlate needs equal-length series (2+)"}
                try:
                    r = statistics.correlation(nums, other)
                except statistics.StatisticsError as e:
                    return {"ok": False, "error": str(e)}
                return {"ok": True, "pearson_r": r}
            if sub == "outliers":
                if len(nums) < 4:
                    return {"ok": False, "error": "need 4+ values"}
                qs = statistics.quantiles(nums, n=4)
                iqr = qs[2] - qs[0]
                lo, hi = qs[0] - 1.5 * iqr, qs[2] + 1.5 * iqr
                return {"ok": True, "outliers": [x for x in nums
                                                 if x < lo or x > hi]}
            if sub == "timeseries":
                return {"ok": True, "first": nums[0], "last": nums[-1],
                        "delta": nums[-1] - nums[0], "points": len(nums)}
        return {"ok": False, "error": f"unknown analytics subtool: {sub!r}"}


def analytics_records() -> list[ToolRecord]:
    return [_rec(f"analytics.{s}", "analytics", s, f"analytics.{s}",
                 "statistics", READ_ONLY, tags=("analytics", "stats"),
                 inschema={"type": "object"})
            for s in ("statistics", "compare", "aggregate", "filter",
                      "correlate", "outliers", "timeseries", "report")]


def analytics_records() -> list[ToolRecord]:
    return [_rec(f"analytics.{s}", "analytics", s, f"analytics.{s}",
                 "statistics", READ_ONLY, tags=("analytics", "stats"),
                 inschema={"type": "object"})
            for s in ("statistics", "compare", "aggregate", "filter",
                      "correlate", "outliers", "timeseries", "report")]


# -- science / units (deterministic tables; never model guesses) ---------------
LENGTH_M = {"m": 1.0, "km": 1000.0, "cm": 0.01, "mm": 0.001, "ft": 0.3048,
            "in": 0.0254, "yd": 0.9144, "mi": 1609.344}
MASS_KG = {"kg": 1.0, "g": 0.001, "mg": 1e-6, "lb": 0.45359237,
           "oz": 0.028349523125, "t": 1000.0}
TIME_S = {"s": 1.0, "min": 60.0, "h": 3600.0, "day": 86400.0, "ms": 0.001}

CONSTANTS = {"c_m_s": 299792458.0, "g_m_s2": 9.80665, "h_J_s": 6.62607015e-34,
             "kB_J_K": 1.380649e-23, "NA_per_mol": 6.02214076e23,
             "e_C": 1.602176634e-19}


class ScienceAdapter(_Ctx):
    def probe(self):
        libs = {}
        for mod in ("numpy", "scipy", "sympy", "matplotlib"):
            try:
                __import__(mod)
                libs[mod] = True
            except ImportError:
                libs[mod] = False
        return {"available": True, "status": AVAILABLE,
                "libraries": libs,
                "reason": "deterministic stdlib tables always; libs optional"}

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        if sub == "units.convert":
            try:
                value = float(arguments.get("value", 0))
            except (TypeError, ValueError):
                return {"ok": False, "error": "'value' must be numeric"}
            frm, to = str(arguments.get("from", "")), str(arguments.get("to", ""))
            if frm == to and frm:
                return {"ok": True, "value": value, "unit": to, "verified": True}
            conv = self._convert(value, frm, to)
            if conv is None:
                return {"ok": False,
                        "error": f"unsupported conversion {frm!r}->{to!r}"}
            return {"ok": True, "value": conv, "unit": to, "verified": True,
                    "method": "deterministic table (never model-guessed)"}
        if sub == "units":
            return {"ok": True, "length_m": LENGTH_M, "mass_kg": MASS_KG,
                    "time_s": TIME_S, "temperature": "celsius/fahrenheit/kelvin"}
        if sub == "constants":
            return {"ok": True, "constants": CONSTANTS}
        if sub in ("calculate", "numeric"):
            expr = str(arguments.get("expression", ""))
            import ast as _ast
            import operator as _op
            allowed = {_ast.Expression: None, _ast.BinOp: None, _ast.UnaryOp: None,
                       _ast.Constant: None, _ast.Add: _op.add, _ast.Sub: _op.sub,
                       _ast.Mult: _op.mul, _ast.Div: _op.truediv,
                       _ast.Pow: _op.pow, _ast.Mod: _op.mod,
                       _ast.USub: _op.neg, _ast.UAdd: _op.pos,
                       _ast.FloorDiv: _op.floordiv}
            try:
                tree = _ast.parse(expr, mode="eval")

                def _ev(n):
                    if isinstance(n, _ast.Expression):
                        return _ev(n.body)
                    if isinstance(n, _ast.Constant) and isinstance(
                            n.value, (int, float)):
                        return float(n.value)
                    if isinstance(n, _ast.BinOp) and type(n.op) in allowed \
                            and allowed[type(n.op)]:
                        return allowed[type(n.op)](_ev(n.left), _ev(n.right))
                    if isinstance(n, _ast.UnaryOp) and type(n.op) in allowed \
                            and allowed[type(n.op)]:
                        return allowed[type(n.op)](_ev(n.operand))
                    raise ValueError("unsafe expression")

                for node in _ast.walk(tree):
                    if type(node) not in allowed:
                        return {"ok": False,
                                "error": "only numeric arithmetic allowed"}
                return {"ok": True, "value": _ev(tree), "verified": True}
            except (ValueError, ZeroDivisionError, SyntaxError) as e:
                return {"ok": False, "error": f"bad expression: {e}"}
        if sub in ("simulate", "equation", "symbolic"):
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    "error": f"science.{sub} needs a CAS/simulator backend"}
        if sub == "units_table":
            return {"ok": True, "tables": "see science.units"}
        if sub == "plot":
            pts = arguments.get("points", [])
            if not isinstance(pts, list) or not pts:
                return {"ok": False, "error": "plot needs 'points' list"}
            svg = self._svg(pts)
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
        return {"ok": False, "error": f"unknown science subtool: {sub!r}"}

    @staticmethod
    def _convert(value: float, frm: str, to: str):
        f, t = frm.strip(), to.strip()
        for table in (LENGTH_M, MASS_KG, TIME_S):
            if f in table and t in table:
                return value * table[f] / table[t]
        tc = {"celsius", "fahrenheit", "kelvin", "c", "f", "k"}
        if f.lower() in tc and t.lower() in tc:
            c = {"celsius": value, "c": value,
                 "fahrenheit": (value - 32) * 5 / 9,
                 "f": (value - 32) * 5 / 9,
                 "kelvin": value - 273.15, "k": value - 273.15}[f.lower()]
            out = {"celsius": c, "c": c,
                   "fahrenheit": c * 9 / 5 + 32, "f": c * 9 / 5 + 32,
                   "kelvin": c + 273.15, "k": c + 273.15}[t.lower()]
            return out
        return None

    @staticmethod
    def _svg(pts: list) -> str:
        try:
            pairs = [(float(p[0]), float(p[1])) for p in pts if len(p) == 2]
        except (TypeError, ValueError, IndexError):
            pairs = []
        if not pairs:
            return "<svg xmlns='http://www.w3.org/2000/svg'></svg>"
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        dx, dy = (x1 - x0) or 1.0, (y1 - y0) or 1.0
        dots = " ".join(
            f"<circle cx='{20 + 460 * (x - x0) / dx:.1f}' "
            f"cy='{280 - 240 * (y - y0) / dy:.1f}' r='3' fill='navy'/>"
            for x, y in pairs[:500])
        return (f"<svg xmlns='http://www.w3.org/2000/svg' width='500' "
                f"height='300'>{dots}</svg>")


def science_records() -> list[ToolRecord]:
    out = []
    for tid in ("science.calculate", "science.simulate", "science.units",
                "science.constants", "science.equation", "science.symbolic",
                "science.numeric", "science.plot", "science.units.convert"):
        real = tid in ("science.calculate", "science.units", "science.constants",
                       "science.numeric", "science.plot", "science.units.convert")
        if real:
            out.append(_rec(tid, "science", tid.split(".", 1)[1], tid,
                            "stdlib tables", READ_ONLY, tags=("science",),
                            inschema={"type": "object"}))
        else:
            out.append(_rec(tid, "science", tid.split(".", 1)[1],
                            tid + " (interface)", "none", READ_ONLY,
                            status=PROVIDER_REQUIRED, available=False,
                            installed=False, provider="CAS/simulator",
                            tags=("science",), inschema={"type": "object"},
                            needs_install="CAS or simulator backend"))
    return out
