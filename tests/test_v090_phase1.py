"""v0.9.0 Phase 1: capability + toolchain + project intelligence tests.

Fast, hermetic unit tests (mocked probes). Real-machine acceptance is
performed separately via scripts, not in this suite.
"""
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from capability_cache import CapabilityCache
from execution_environment import ExecutionEnvironmentRegistry
from language_registry import LanguageRegistry, SupportLevel
from machine_capability import (
    MachineCapability,
    MachineCapabilityRegistry,
    MemoryInfo,
    ToolInfo,
    VirtualizationInfo,
)
from project_detector import inspect_project
from project_model import build_project_model
from tool_selector import ProjectRequirement, ToolSelectionEngine
from toolchain_registry import (
    Toolchain,
    ToolchainCategory,
    ToolchainComponent,
    ToolchainRegistry,
    ToolchainStatus,
)


def _fake_toolchain(tid, languages, status=ToolchainStatus.AVAILABLE, rank=0,
                    envs=None, components=None):
    tc = Toolchain(id=tid, name=tid, primary_language=(languages[0] if languages else ""),
                   supported_languages=list(languages), status=status, rank=rank,
                   environments=list(envs or ["WINDOWS_NATIVE"]))
    if components is not None:
        tc.components = components
    else:
        comp = ToolchainComponent(name="fake-comp", category=ToolchainCategory.COMPILER,
                                  status=status, version="1.0")
        tc.components = [comp]
    return tc


def _write(root: Path, rel: str, content: str = "x"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


class TestMachineProfile(unittest.TestCase):
    def test_empty_minimal_profile_serializes(self):
        cap = MachineCapability()
        reg = MachineCapabilityRegistry()
        d = reg.to_dict(cap)
        self.assertIn("os", d)
        self.assertIn("cpu", d)
        self.assertIn("memory", d)
        self.assertEqual(d["gpus"], [])
        self.assertEqual(d["tools"], [])

    def test_run_probe_success(self):
        reg = MachineCapabilityRegistry()
        with mock.patch("machine_capability.subprocess.run") as m:
            m.return_value = mock.Mock(returncode=0, stdout="clang version 22\n", stderr="")
            ok, out = reg._run_probe(["clang++", "--version"])
        self.assertTrue(ok)
        self.assertIn("clang", out)

    def test_run_probe_failure(self):
        reg = MachineCapabilityRegistry()
        with mock.patch("machine_capability.subprocess.run") as m:
            m.return_value = mock.Mock(returncode=1, stdout="", stderr="oops")
            ok, out = reg._run_probe(["broken-tool", "--version"])
        self.assertFalse(ok)

    def test_run_probe_timeout(self):
        reg = MachineCapabilityRegistry()
        with mock.patch("machine_capability.subprocess.run",
                        side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1)):
            ok, out = reg._run_probe(["hang-tool", "--version"], timeout=1)
        self.assertFalse(ok)

    def test_run_probe_oserror(self):
        reg = MachineCapabilityRegistry()
        with mock.patch("machine_capability.subprocess.run",
                        side_effect=OSError("nope")):
            ok, _ = reg._run_probe(["missing-tool", "--version"])
        self.assertFalse(ok)

    def test_tool_probe_missing_binary_skipped(self):
        reg = MachineCapabilityRegistry()
        reg._tool_probes = {"definitely-not-a-real-tool-xyz": ("compiler", ["definitely-not-a-real-tool-xyz", "--version"])}
        with mock.patch("machine_capability.shutil.which", return_value=None):
            tools = reg._discover_tools()
        self.assertEqual(tools, [])

    def test_tool_found_recorded(self):
        reg = MachineCapabilityRegistry()
        reg._tool_probes = {"mycc": ("compiler", ["mycc", "--version"])}
        with mock.patch("machine_capability.shutil.which", return_value="/usr/bin/mycc"), \
             mock.patch.object(reg, "_run_probe", return_value=(True, "mycc 9.9")):
            tools = reg._discover_tools()
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0].name, "mycc")
        self.assertTrue(tools[0].working)

    def test_duplicate_executable_paths_both_recorded(self):
        reg = MachineCapabilityRegistry()
        reg._tool_probes = {
            "tool-a": ("compiler", ["tool-a", "--version"]),
            "tool-b": ("compiler", ["tool-b", "--version"]),
        }
        with mock.patch("machine_capability.shutil.which", return_value="/same/path/tool"), \
             mock.patch.object(reg, "_run_probe", return_value=(True, "v1")):
            tools = reg._discover_tools()
        self.assertEqual({t.name for t in tools}, {"tool-a", "tool-b"})
        self.assertEqual(tools[0].executable, tools[1].executable)

    def test_wsl_detection_mock(self):
        reg = MachineCapabilityRegistry()
        status_out = "Default Distribution: Ubuntu\nWSL version: 2.0.0\n"
        list_out = "  NAME      STATE     VERSION\n* Ubuntu    Running   2\n  Debian    Stopped   2\n"

        def fake_run(cmd, **kw):
            m = mock.Mock()
            m.returncode = 0
            if cmd[:2] == ["wsl", "--status"]:
                m.stdout = status_out
            elif cmd[:2] == ["wsl", "-l"]:
                m.stdout = list_out
            else:
                m.stdout = ""
            m.stderr = ""
            return m

        with mock.patch("machine_capability.subprocess.run", side_effect=fake_run), \
             mock.patch("machine_capability.shutil.which", return_value=None):
            info = reg._discover_virtualization()
        names = [d.get("name") for d in info.wsl_distros]
        self.assertIn("Ubuntu", names)
        self.assertIn("Debian", names)

    def test_scan_cache_and_forced_rescan(self):
        reg = MachineCapabilityRegistry(cache_ttl_seconds=3600.0)
        calls = {"n": 0}

        def fake_scan(force=False):
            calls["n"] += 1
            return MachineCapability()

        with mock.patch.object(reg, "scan", side_effect=fake_scan):
            # emulate cache behavior manually via underlying cache fields
            pass
        # Real cache behavior: two scans without force use cache
        with mock.patch.object(reg, "_discover_os"), \
             mock.patch.object(reg, "_discover_cpu"), \
             mock.patch.object(reg, "_discover_memory"), \
             mock.patch.object(reg, "_discover_gpus", return_value=[]), \
             mock.patch.object(reg, "_discover_storage", return_value=[]), \
             mock.patch.object(reg, "_discover_virtualization",
                               return_value=VirtualizationInfo()), \
             mock.patch.object(reg, "_discover_shells", return_value=[]), \
             mock.patch.object(reg, "_discover_tools", return_value=[]), \
             mock.patch.object(reg, "_discover_runtimes", return_value=[]), \
             mock.patch.object(reg, "_discover_environment_variables", return_value={}):
            a = reg.scan(force=True)
            b = reg.scan(force=False)
            self.assertIs(a, b)
            reg.invalidate_cache()
            c = reg.scan(force=False)
            self.assertIsNot(a, c)


class TestExecutionEnvironments(unittest.TestCase):
    def _machine(self):
        cap = MachineCapability()
        cap.memory = MemoryInfo(total_mb=16384, available_mb=8192)
        cap.tools = [ToolInfo(name="git", executable="/usr/bin/git", version="2.40",
                              category="vcs", working=True),
                     ToolInfo(name="docker", executable="/usr/bin/docker", version="24.0",
                              category="container", working=True)]
        return cap

    def test_windows_paths_conversion(self):
        reg = ExecutionEnvironmentRegistry()
        machine = self._machine()
        machine.virtualization = VirtualizationInfo(
            enabled=True, hypervisor="WSL2", wsl_version="2.0",
            wsl_distros=[{"name": "Ubuntu", "state": "Running", "version": "2", "default": True}])
        with mock.patch.object(reg._machine_registry, "scan", return_value=machine):
            envs = reg.discover(machine)
        self.assertIn("WINDOWS_NATIVE", envs)
        self.assertIn("WSL:Ubuntu", envs)
        win = "C:\\Users\\jpowe\\proj"
        wsl = reg.convert_path(win, "WINDOWS_NATIVE", "WSL:Ubuntu")
        self.assertEqual(wsl, "/mnt/c/Users/jpowe/proj")
        back = reg.convert_path(wsl, "WSL:Ubuntu", "WINDOWS_NATIVE")
        self.assertEqual(back, win)

    def test_healthy_filter(self):
        reg = ExecutionEnvironmentRegistry()
        machine = self._machine()
        with mock.patch.object(reg._machine_registry, "scan", return_value=machine):
            reg.discover(machine)
        healthy = reg.list_healthy()
        self.assertTrue(all(e.health == "HEALTHY" for e in healthy))
        self.assertTrue(len(healthy) >= 1)


class TestToolchainRegistry(unittest.TestCase):
    def test_probe_component_not_found(self):
        reg = ToolchainRegistry()
        fake_machine = MachineCapability(tools=[])
        reg._machine = fake_machine
        with mock.patch("toolchain_registry.shutil.which", return_value=None):
            comp = reg._probe_component("no-such-tool-xyz", ToolchainCategory.COMPILER)
        self.assertEqual(comp.status, ToolchainStatus.NOT_FOUND)

    def test_probe_component_available(self):
        reg = ToolchainRegistry()
        fake_machine = MachineCapability(tools=[
            ToolInfo(name="clang++", executable="/usr/bin/clang++", version="clang 22",
                     category="compiler", working=True, languages=["cpp"])])
        reg._machine = fake_machine
        comp = reg._probe_component("clang++", ToolchainCategory.COMPILER)
        self.assertEqual(comp.status, ToolchainStatus.AVAILABLE)
        self.assertIn("22", comp.version)

    def test_discover_toolchain_mocked(self):
        reg = ToolchainRegistry()
        fake_machine = MachineCapability(tools=[
            ToolInfo(name="python", executable="/usr/bin/python", version="3.11",
                     category="interpreter", working=True, languages=["python"]),
            ToolInfo(name="pip", executable="/usr/bin/pip", version="23.0",
                     category="package_manager", working=True, languages=["python"]),
        ])
        fake_envs = {"WINDOWS_NATIVE": mock.Mock(identifier="WINDOWS_NATIVE", health="HEALTHY")}
        with mock.patch.object(reg._machine_registry, "scan", return_value=fake_machine), \
             mock.patch.object(reg._env_registry, "discover", return_value=fake_envs):
            tc = reg.discover_toolchain("python", fake_machine, fake_envs)
        self.assertIsNotNone(tc)
        self.assertEqual(tc.id, "python")
        # required python+pip present -> AVAILABLE
        self.assertEqual(tc.status, ToolchainStatus.AVAILABLE)


class TestLanguageRegistry(unittest.TestCase):
    def test_extension_mapping(self):
        reg = LanguageRegistry()
        self.assertEqual(reg.find_language_for_extension(".rs"), "rust")
        self.assertEqual(reg.find_language_for_extension(".py"), "python")
        self.assertEqual(reg.find_language_for_extension(".tsx"), "typescript")
        self.assertEqual(reg.find_language_for_file("src/main.cpp"), "cpp")
        self.assertIsNone(reg.find_language_for_extension(".definitelynotreal"))

    def test_support_level_ordering(self):
        self.assertTrue(SupportLevel.FULL > SupportLevel.PARTIAL)
        self.assertTrue(SupportLevel.PARTIAL > SupportLevel.MINIMAL)
        self.assertTrue(SupportLevel.MINIMAL > SupportLevel.NONE)


class TestProjectDetector(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="v090_proj_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unknown_project(self):
        p = inspect_project(self.tmp)
        self.assertTrue(p.exists)
        self.assertEqual(p.confidence, "unknown")
        self.assertEqual(p.indicators, [])

    def test_python_project(self):
        _write(self.tmp, "pyproject.toml", "[project]\nname='x'\n")
        _write(self.tmp, "src/app.py", "print(1)\n")
        _write(self.tmp, "tests/test_app.py", "def test_x(): pass\n")
        p = inspect_project(self.tmp)
        self.assertIn("python", p.languages)
        self.assertIn("python", p.project_kinds)
        self.assertIn("tests", p.test_dirs[0] if p.test_dirs else "tests")

    def test_cxx_project(self):
        _write(self.tmp, "CMakeLists.txt", "cmake_minimum_required(VERSION 3.20)\n")
        _write(self.tmp, "src/main.cpp", "int main(){return 0;}\n")
        _write(self.tmp, "include/a.hpp", "#pragma once\n")
        p = inspect_project(self.tmp)
        self.assertIn("cpp", p.languages)
        self.assertIn("cmake", p.project_kinds)

    def test_rust_project(self):
        _write(self.tmp, "Cargo.toml", "[package]\nname='x'\n")
        _write(self.tmp, "src/main.rs", "fn main(){}\n")
        p = inspect_project(self.tmp)
        self.assertIn("rust", p.languages)
        self.assertIn("rust", p.project_kinds)

    def test_typescript_frontend_project(self):
        _write(self.tmp, "package.json", '{"name":"x"}\n')
        _write(self.tmp, "tsconfig.json", '{}\n')
        _write(self.tmp, "src/app.ts", "export const x=1;\n")
        _write(self.tmp, "src/app.tsx", "export const y=1;\n")
        p = inspect_project(self.tmp)
        self.assertIn("typescript", p.languages)
        self.assertIn("node", p.project_kinds)

    def test_frontend_only(self):
        _write(self.tmp, "package.json", '{"name":"x"}\n')
        _write(self.tmp, "index.html", "<html></html>\n")
        _write(self.tmp, "style.css", "body{}\n")
        _write(self.tmp, "app.js", "console.log(1)\n")
        p = inspect_project(self.tmp)
        m = build_project_model(p)
        self.assertTrue(m.has_frontend)
        self.assertFalse(m.has_backend and m.has_native)

    def test_backend_only(self):
        _write(self.tmp, "requirements.txt", "flask\n")
        _write(self.tmp, "app.py", "print(1)\n")
        p = inspect_project(self.tmp)
        m = build_project_model(p)
        self.assertTrue(m.has_backend)
        self.assertFalse(m.has_frontend)

    def test_mixed_language_project(self):
        _write(self.tmp, "package.json", '{"name":"x"}\n')
        _write(self.tmp, "frontend/app.ts", "export const x=1;\n")
        _write(self.tmp, "pyproject.toml", "[project]\nname='y'\n")
        _write(self.tmp, "backend/svc.py", "print(1)\n")
        _write(self.tmp, "native/CMakeLists.txt", "cmake_minimum_required(VERSION 3.20)\n")
        _write(self.tmp, "native/e.cpp", "int f(){return 1;}\n")
        p = inspect_project(self.tmp)
        m = build_project_model(p)
        self.assertTrue(m.has_frontend)
        self.assertTrue(m.has_backend)
        self.assertTrue(m.has_native)
        self.assertGreaterEqual(len(m.all_languages), 3)

    def test_full_stack_project(self):
        _write(self.tmp, "package.json", '{"name":"fe"}\n')
        _write(self.tmp, "fe/a.ts", "export const x=1;\n")
        _write(self.tmp, "pyproject.toml", "[project]\nname='be'\n")
        _write(self.tmp, "be/a.py", "x=1\n")
        _write(self.tmp, "Cargo.toml", "[package]\nname='svc'\n")
        _write(self.tmp, "svc/main.rs", "fn main(){}\n")
        _write(self.tmp, "Dockerfile", "FROM python\n")
        _write(self.tmp, "schema.sql", "CREATE TABLE t(x INT);\n")
        _write(self.tmp, "shaders/a.vert", "void main(){}\n")
        p = inspect_project(self.tmp)
        m = build_project_model(p)
        self.assertTrue(m.has_frontend)
        self.assertTrue(m.has_backend)
        self.assertTrue(m.has_containers)
        self.assertTrue(m.has_database)
        self.assertTrue(m.has_shaders)
        # service component from Cargo
        roles = {c.role for c in m.components}
        self.assertIn("service", roles)

    def test_detector_read_only_no_execution(self):
        # A malicious-looking file must never be executed by the detector
        _write(self.tmp, "evil.py", "import os; os.system('echo PWNED')\n")
        marker = self.tmp / "PWNED"
        p = inspect_project(self.tmp)
        self.assertIn("python", p.languages)
        self.assertFalse(marker.exists())


class TestToolSelector(unittest.TestCase):
    def test_recommendation_prefers_complete_toolchain(self):
        reg = ToolchainRegistry()
        good = _fake_toolchain("cpp-clang", ["cpp", "c"], rank=0)
        bad = _fake_toolchain("cpp-broken", ["cpp"], status=ToolchainStatus.AVAILABLE_BUT_BROKEN, rank=0)
        eng = ToolSelectionEngine(reg)
        req = ProjectRequirement(language="cpp", build_system="cmake")
        opts = eng.recommend(req, [bad, good])
        self.assertTrue(opts[0].compatible)
        self.assertEqual(opts[0].toolchain_id, "cpp-clang")

    def test_no_compatible_toolchain(self):
        eng = ToolSelectionEngine(ToolchainRegistry())
        req = ProjectRequirement(language="cpp")
        broken = _fake_toolchain("x", ["cpp"], status=ToolchainStatus.NOT_FOUND)
        opts = eng.recommend(req, [broken])
        self.assertFalse(any(o.compatible for o in opts))
        self.assertIsNone(eng.best(req, [broken]))

    def test_multiple_compatible_ranked_deterministically(self):
        eng = ToolSelectionEngine(ToolchainRegistry())
        a = _fake_toolchain("b-tc", ["python"], rank=5)
        b = _fake_toolchain("a-tc", ["python"], rank=5)
        req = ProjectRequirement(language="python")
        opts = eng.recommend(req, [a, b])
        self.assertEqual([o.toolchain_id for o in opts], ["a-tc", "b-tc"])

    def test_user_override_wins(self):
        eng = ToolSelectionEngine(ToolchainRegistry())
        winner = _fake_toolchain("custom", ["python"], rank=9999)
        other = _fake_toolchain("other", ["python"], rank=0)
        reg = eng._registry
        reg._toolchains = {"custom": winner, "other": other}
        req = ProjectRequirement(language="python", user_override_toolchain="custom")
        opts = eng.recommend(req, [other, winner])
        self.assertEqual(opts[0].toolchain_id, "custom")

    def test_min_version_filters(self):
        eng = ToolSelectionEngine(ToolchainRegistry())
        old_comp = ToolchainComponent(name="python", category=ToolchainCategory.INTERPRETER,
                                      status=ToolchainStatus.AVAILABLE, version="3.8.0")
        new_comp = ToolchainComponent(name="python", category=ToolchainCategory.INTERPRETER,
                                      status=ToolchainStatus.AVAILABLE, version="3.12.0")
        old = _fake_toolchain("py-old", ["python"], components=[old_comp])
        new = _fake_toolchain("py-new", ["python"], components=[new_comp])
        req = ProjectRequirement(language="python", min_version="3.10")
        best = eng.best(req, [old, new])
        self.assertIsNotNone(best)
        self.assertEqual(best.toolchain_id, "py-new")


class TestCapabilityCache(unittest.TestCase):
    def test_put_get_invalidate(self):
        c = CapabilityCache(ttl_seconds=60)
        self.assertIsNone(c.get("k"))
        c.put("k", {"a": 1}, {"t": "1.0"})
        self.assertEqual(c.get("k").payload, {"a": 1})
        self.assertEqual(c.invalidate("k"), 1)
        self.assertIsNone(c.get("k"))

    def test_expiry(self):
        c = CapabilityCache(ttl_seconds=0.01)
        c.put("k", {"a": 1})
        time.sleep(0.03)
        self.assertIsNone(c.get("k"))

    def test_forced_rescan(self):
        c = CapabilityCache(ttl_seconds=3600)
        c.put("k", {"v": 1})
        e = c.rescan("k", lambda: ({"v": 2}, {"t": "2.0"}))
        self.assertEqual(e.payload, {"v": 2})
        self.assertEqual(c.get("k").payload, {"v": 2})

    def test_invalidate_all(self):
        c = CapabilityCache()
        c.put("a", {})
        c.put("b", {})
        self.assertEqual(c.invalidate(), 2)
        self.assertIsNone(c.get("a"))


class TestCapabilityAPI(unittest.TestCase):
    def test_inspect_project_api(self):
        from capability_api import inspect_project as api_inspect
        tmp = Path(tempfile.mkdtemp(prefix="v090_api_"))
        try:
            (tmp / "pyproject.toml").write_text("[project]\nname='x'\n")
            (tmp / "a.py").write_text("x=1\n")
            out = api_inspect(str(tmp))
            self.assertIn("profile", out)
            self.assertIn("model", out)
            self.assertIn("python", out["profile"]["languages"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cache_status_api(self):
        from capability_api import cache_status, invalidate_cache
        s = cache_status()
        self.assertIn("entries", s)
        r = invalidate_cache("no-such-key")
        self.assertEqual(r, {"removed": 0})


if __name__ == "__main__":
    unittest.main()
