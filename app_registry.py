"""Canonical installed-application registry: the machine-readable record of
which installed applications exist on this host (engineering tools and AI
agent tooling), what each can do, how it is driven, and whether that claim
was ever tested.

This is a NEW owner because none existed: execution_environment.py owns
*runtimes* (native shell, WSL, docker); nothing owned *installed desktop
applications* with their capability families, formats and verification
state. This module does not execute, authorize or schedule anything -- it
describes, so Genesis can later select the right tool automatically.

Verification vocabulary (closed):
- UNVERIFIED ..... discovered but never executed
- PARTIAL ....... executed with a documented limitation or blocker
- VERIFIED ...... launched, real test completed, output verified
- INTERACTIVE_ONLY  installed, usable by a human, no automation interface
- ABSENT ........ checked for and not present
- BLOCKED_OWNER . needs elevation, purchase, account or other owner action
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

STATUSES = (
    "UNVERIFIED",
    "PARTIAL",
    "VERIFIED",
    "INTERACTIVE_ONLY",
    "ABSENT",
    "BLOCKED_OWNER",
)


@dataclass(frozen=True)
class ApplicationRecord:
    app_id: str
    name: str
    version: str
    executable: str
    install_path: str
    license: str
    capability_families: tuple[str, ...] = ()
    native_formats: tuple[str, ...] = ()
    import_formats: tuple[str, ...] = ()
    export_formats: tuple[str, ...] = ()
    cli: bool = False
    api: bool = False
    scripting: bool = False
    headless: bool = False
    bridge_adapter: str = ""
    verification_status: str = "UNVERIFIED"
    last_verified: str = ""
    limitations: str = ""

    def __post_init__(self) -> None:
        if not self.app_id or " " in self.app_id:
            raise ValueError(f"app_id must be a compact id: {self.app_id!r}")
        if self.verification_status not in STATUSES:
            raise ValueError(f"unknown status {self.verification_status!r}")
        if self.verification_status == "VERIFIED" and not self.bridge_adapter:
            raise ValueError(f"{self.app_id}: VERIFIED requires a bridge adapter")


class AppRegistryError(Exception):
    pass


def expand_record_paths(record: "ApplicationRecord") -> "ApplicationRecord":
    """Expand %VAR% placeholders against the process environment.

    Records store portable placeholders, never a specific user's absolute
    home directory (the secret-hygiene gate refuses personal paths in
    source). Expansion happens at read time, on the machine doing the
    reading, so the same record resolves correctly for any user.
    """
    import os

    def expand(value: str) -> str:
        return os.path.expandvars(value)

    return ApplicationRecord(
        **{**asdict(record),
           "executable": expand(record.executable),
           "install_path": expand(record.install_path)})


class ApplicationRegistry:
    """One registry object per host. Persisted as JSON next to the caller."""

    def __init__(self) -> None:
        self._apps: dict[str, ApplicationRecord] = {}

    def register(self, record: ApplicationRecord) -> ApplicationRecord:
        if record.app_id in self._apps:
            raise AppRegistryError(f"duplicate app_id {record.app_id!r}")
        self._apps[record.app_id] = record
        return record

    def get(self, app_id: str) -> ApplicationRecord:
        try:
            return self._apps[app_id]
        except KeyError:
            raise AppRegistryError(f"unknown app_id {app_id!r}")

    def capability_map(self) -> dict[str, list[str]]:
        """capability family -> sorted app_ids claiming it. Claims, not proof:
        consult verification_status before trusting any entry."""
        out: dict[str, list[str]] = {}
        for app in self._apps.values():
            for family in app.capability_families:
                out.setdefault(family, []).append(app.app_id)
        return {k: sorted(v) for k, v in sorted(out.items())}

    def verified_for(self, family: str) -> list[str]:
        return sorted(a.app_id for a in self._apps.values()
                      if family in a.capability_families
                      and a.verification_status == "VERIFIED")

    def to_dict(self) -> dict:
        return {"applications": [
            {**asdict(a), "capability_families": list(a.capability_families),
             "native_formats": list(a.native_formats),
             "import_formats": list(a.import_formats),
             "export_formats": list(a.export_formats)}
            for a in sorted(self._apps.values(), key=lambda a: a.app_id)]}

    @classmethod
    def from_dict(cls, data: dict) -> "ApplicationRegistry":
        reg = cls()
        for entry in data.get("applications", []):
            reg.register(ApplicationRecord(
                **{**entry,
                   "capability_families": tuple(entry.get("capability_families", ())),
                   "native_formats": tuple(entry.get("native_formats", ())),
                   "import_formats": tuple(entry.get("import_formats", ())),
                   "export_formats": tuple(entry.get("export_formats", ()))}))
        return reg

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "ApplicationRegistry":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def seed_workstation_registry() -> ApplicationRegistry:
    """The measured 2026-10-05 workstation state. Every VERIFIED entry below
    has an executed test behind it; everything else says exactly what it is."""
    reg = ApplicationRegistry()
    reg.register(ApplicationRecord(
        app_id="freecad", name="FreeCAD", version="1.0.2",
        executable="C:/Program Files/FreeCAD 1.0/bin/freecadcmd.exe",
        install_path="C:/Program Files/FreeCAD 1.0",
        license="LGPL-2+",
        capability_families=("PARAMETRIC_CAD", "DIRECT_CAD", "MESH_MODELING",
                              "CNC_CAM", "FEA", "METROLOGY"),
        native_formats=("FCStd",), import_formats=("STEP", "STL", "OBJ", "DXF"),
        export_formats=("STEP", "STL", "OBJ", "DXF"),
        cli=True, api=False, scripting=True, headless=True,
        bridge_adapter="freecad_adapter.py",
        verification_status="VERIFIED", last_verified="2026-10-07",
        limitations="re-verified 2026-10-07: 10x20x30 box, volume 6000.0, STEP 6854B + binary STL 12 facets; freecadcmd exits 0 on script errors; FEM assembly needs ObjectsFEM (headless gap); CAM job creation deferred"))
    reg.register(ApplicationRecord(
        app_id="blender", name="Blender", version="5.2.2 LTS",
        executable="blender-launcher.exe (Store package BlenderFoundation.Blender_5.2.2.0)",
        install_path="C:/Program Files/WindowsApps/BlenderFoundation.Blender_5.2.2.0_x64__ppwjx1n5r4v9t",
        license="GPL (assumed, Store distribution)",
        capability_families=("MESH_MODELING", "RENDERING", "ANIMATION", "SCULPTING"),
        native_formats=(".blend",), import_formats=("STL", "OBJ", "FBX", "glTF"),
        export_formats=("STL", "OBJ", "FBX", "glTF", "PNG"),
        cli=True, api=False, scripting=True, headless=True,
        bridge_adapter="blender_adapter.py",
        verification_status="VERIFIED", last_verified="2026-10-07",
        limitations="re-verified 2026-10-07: version-to-file transcript + Cycles CPU render of default cube (107688B valid PNG); launcher captures no stdout (file transcripts only); headless Eevee fails (no GL context, use Cycles CPU); 5.2 API names differ from 4.x; owner-pinned, never upgrade"))
    reg.register(ApplicationRecord(
        app_id="cura", name="Ultimaker Cura", version="5.13.0",
        executable="C:/Program Files/UltiMaker Cura 5.13.0/CuraEngine.exe",
        install_path="C:/Program Files/UltiMaker Cura 5.13.0",
        license="AGPL-3.0 (CuraEngine)",
        capability_families=("3D_PRINT_SLICING",),
        native_formats=(), import_formats=("STL", "OBJ", "3MF"),
        export_formats=("G-code",),
        cli=True, api=False, scripting=False, headless=True,
        bridge_adapter="cura_adapter.py",
        verification_status="VERIFIED", last_verified="2026-10-07",
        limitations="closure-proven 2026-10-07: standalone slice (10mm box -> 576863B gcode, 298 layers, 13832 G1 moves; roofing/flooring_layer_count=0 required) + Agent Bridge chain supervisor->worker->cura_adapter->CuraEngine->verified gcode (supervised-workers Path C); definitions resolved from install share"))
    reg.register(ApplicationRecord(
        app_id="kicad", name="KiCad", version="10.0.6",
        executable="%LOCALAPPDATA%/Programs/KiCad/10.0/bin/kicad-cli.exe",
        install_path="%LOCALAPPDATA%/Programs/KiCad/10.0",
        license="GPL-3.0+",
        capability_families=("ELECTRONICS", "PCB"),
        native_formats=(".kicad_sch", ".kicad_pcb"), import_formats=(),
        export_formats=("Gerber", "Excellon", "PDF", "netlist"),
        cli=True, api=True, scripting=False, headless=True,
        bridge_adapter="",
        verification_status="PARTIAL", last_verified="2026-10-07",
        limitations="re-verified 2026-10-07: full Battery.pretty library exported to SVG plots (31-46KB each); kicad-cli has NO create-project subcommand (fp/jobset/pcb/sch/sym/version only); hand-authored minimal schematics do not load (v10 strict format); PCB/DRC/Gerber untested; no bridge adapter yet"))
    reg.register(ApplicationRecord(
        app_id="shapr3d", name="Shapr3D", version="26.170",
        executable="(Store app, no CLI)", install_path="(Store package)",
        license="commercial (owner-licensed)",
        capability_families=("PARAMETRIC_CAD", "DIRECT_CAD"),
        native_formats=(), import_formats=(), export_formats=(),
        cli=False, api=False, scripting=False, headless=False,
        bridge_adapter="",
        verification_status="INTERACTIVE_ONLY", last_verified="2026-10-05",
        limitations="no automation interface found"))
    reg.register(ApplicationRecord(
        app_id="solvespace", name="SolveSpace", version="3.2",
        executable="%USERPROFILE%/AetheriusTools/solvespace/solvespace.exe",
        install_path="%USERPROFILE%/AetheriusTools/solvespace",
        license="GPL-3.0",
        capability_families=("CSG_CAD", "PARAMETRIC_CAD"),
        native_formats=(".slvs",), import_formats=(), export_formats=("STL", "STEP"),
        cli=False, api=False, scripting=False, headless=False,
        bridge_adapter="",
        verification_status="INTERACTIVE_ONLY", last_verified="2026-10-05",
        limitations="single-exe portable install verified present; hangs on --help (GUI-only, killed)"))
    reg.register(ApplicationRecord(
        app_id="colmap", name="COLMAP", version="4.2.1 (CPU, no GPU)",
        executable="%USERPROFILE%/AetheriusTools/colmap/bin/bin/colmap.exe",
        install_path="%USERPROFILE%/AetheriusTools/colmap",
        license="BSD-3-Clause",
        capability_families=("PHOTOGRAMMETRY", "POINT_CLOUD"),
        native_formats=(), import_formats=("JPG", "PNG"), export_formats=("PLY", "NVM"),
        cli=True, api=False, scripting=False, headless=True,
        bridge_adapter="",
        verification_status="PARTIAL", last_verified="2026-10-07",
        limitations="retested 2026-10-07: feature_extractor RUNS (prior 0xC0000409 crash NOT reproduced) but needs QT_QPA_PLATFORM_PLUGIN_PATH=<install>/bin/plugins/platforms; GPU SIFT matcher yields 0 matches headless (no GL) - CPU flag namespace is --FeatureMatching.use_gpu (4.x); full chain closed 2026-10-07: Blender 10 textured views -> extract (500-950 SIFT/view w/ relaxed thresholds) -> CPU match -> mapper, but init rejects (best 55 inliers; synthetic repetitive texture aliases, even init_min_num_inliers=30 triangulates bad); needs REAL textured photos for a model; no bridge adapter yet"))
    reg.register(ApplicationRecord(
        app_id="gmsh", name="Gmsh", version="4.15.2 (pip API)",
        executable="(Python API, pip user install)",
        install_path="(site-packages)",
        license="GPL-2.0+",
        capability_families=("MESHING",),
        native_formats=(".msh",), import_formats=("STEP", "STL", "BREP"),
        export_formats=(".msh",),
        cli=False, api=True, scripting=True, headless=True,
        bridge_adapter="",
        verification_status="PARTIAL", last_verified="2026-10-05",
        limitations="API meshes STL in 0.2s proven; CLI binary not installed; CalculiX .inp export path untested"))
    reg.register(ApplicationRecord(
        app_id="orcaslicer", name="OrcaSlicer", version="2.4.2 (portable)",
        executable="%USERPROFILE%/AetheriusTools/orcaslicer/app/orca-slicer.exe",
        install_path="%USERPROFILE%/AetheriusTools/orcaslicer",
        license="AGPL-3.0",
        capability_families=("3D_PRINT_SLICING",),
        native_formats=(), import_formats=("STL", "STEP", "3MF"),
        export_formats=("G-code",),
        cli=False, api=False, scripting=False, headless=False,
        bridge_adapter="",
        verification_status="INTERACTIVE_ONLY", last_verified="2026-10-05",
        limitations="no headless slice flags (--slice/--export-gcode rejected); manual fallback only"))
    # Corrected 2026-10-07: the 2026-10-06 "not installed" verdicts below were
    # wrong. All seven were found live (uninstall registry + Start Menu +
    # executed) and re-measured. Live machine state wins over old reports.
    reg.register(ApplicationRecord(
        app_id="openscad", name="OpenSCAD", version="2021.01",
        executable="C:/Program Files/OpenSCAD/openscad.exe",
        install_path="C:/Program Files/OpenSCAD",
        license="GPL-2.0+",
        capability_families=("PARAMETRIC_CAD", "CSG_CAD"),
        native_formats=(".scad",), import_formats=("STL", "DXF", "OFF"),
        export_formats=("STL", "OFF", "DXF", "CSG"),
        cli=True, api=False, scripting=False, headless=True,
        bridge_adapter="",
        verification_status="PARTIAL", last_verified="2026-10-07",
        limitations="headless CGAL render proven 2026-10-07 (cube-minus-cylinder -> 8729B STL, 16 facets, 2.4s); uninstall entry oddly named 'OpenSCAD (remove only)' but install is healthy; no bridge adapter yet"))
    reg.register(ApplicationRecord(
        app_id="librecad", name="LibreCAD", version="2.2.1.5",
        executable="C:/Program Files/LibreCAD/LibreCAD.exe",
        install_path="C:/Program Files/LibreCAD",
        license="GPL-2.0",
        capability_families=("2D_DRAWING",),
        native_formats=(".dxf",), import_formats=("DXF", "DWG"),
        export_formats=("DXF", "PDF", "SVG"),
        cli=False, api=False, scripting=False, headless=False,
        bridge_adapter="",
        verification_status="INTERACTIVE_ONLY", last_verified="2026-10-07",
        limitations="installed + Start Menu shortcut healthy; --help prints debug header only, no automation interface; GUI use deferred to owner"))
    reg.register(ApplicationRecord(
        app_id="inkscape", name="Inkscape", version="1.4.4",
        executable="%PROGRAMFILES%/WindowsApps/25415Inkscape.Inkscape_1.4.40.0_x64__9waqn51p1ttv2/VFS/ProgramFilesX64/Inkscape/bin/inkscape.exe",
        install_path="(MSIX package 25415Inkscape.Inkscape_1.4.40.0_x64)",
        license="GPL-3.0+",
        capability_families=("VECTOR_GRAPHICS", "2D_DRAWING"),
        native_formats=(".svg",), import_formats=("SVG", "PDF", "EPS", "PNG"),
        export_formats=("SVG", "PDF", "EPS", "PNG"),
        cli=False, api=False, scripting=False, headless=False,
        bridge_adapter="",
        verification_status="INTERACTIVE_ONLY", last_verified="2026-10-07",
        limitations="Store (MSIX) install: direct-exe launch is Access-denied by sandbox, no execution alias; GUI via Start Menu shortcut only; empty portable dirs sit unused under %USERPROFILE%/AetheriusTools/inkscape"))
    reg.register(ApplicationRecord(
        app_id="cloudcompare", name="CloudCompare", version="2.13.2",
        executable="%USERPROFILE%/AetheriusTools/cloudcompare/CloudCompare_v2.13.2.preview_bin_x64/CloudCompare.exe",
        install_path="%USERPROFILE%/AetheriusTools/cloudcompare/CloudCompare_v2.13.2.preview_bin_x64",
        license="GPL-2.0+",
        capability_families=("POINT_CLOUD", "METROLOGY", "REVERSE_ENGINEERING"),
        native_formats=(".bin",), import_formats=("PLY", "LAS", "E57", "PTS", "STL"),
        export_formats=("PLY", "LAS", "E57", "BIN"),
        cli=True, api=False, scripting=False, headless=True,
        bridge_adapter="",
        verification_status="PARTIAL", last_verified="2026-10-07",
        limitations="portable x64 proven headless 2026-10-07: -SILENT load box.stl -> save .bin, 0.63s; bare --version prints nothing and bare flags can hang awaiting GUI (kill strays); Downloads holds a WRONG-ARCH ARM64 installer (unusable on x64); no bridge adapter yet"))
    reg.register(ApplicationRecord(
        app_id="camotics", name="CAMotics", version="1.2.0",
        executable="C:/Program Files (x86)/CAMotics/camotics.exe",
        install_path="C:/Program Files (x86)/CAMotics",
        license="GPL-2.0+",
        capability_families=("CNC_SIMULATION",),
        native_formats=(".camotics",), import_formats=("G-code", "TPL"),
        export_formats=("STL",),
        cli=True, api=False, scripting=False, headless=True,
        bridge_adapter="",
        verification_status="PARTIAL", last_verified="2026-10-07",
        limitations="camsim.exe CLI proven 2026-10-07: shipped box.camotics project -> 5.9MB STL, 117732 tris simmed; bare g-code WITHOUT tool/stock definitions removes nothing (0 tris, valid empty STL); needs .camotics project (tool+stock) for meaningful sims; no bridge adapter yet"))
    reg.register(ApplicationRecord(
        app_id="lasergrbl", name="LaserGRBL", version="7.14.1",
        executable="C:/Program Files (x86)/LaserGRBL/LaserGRBL.exe",
        install_path="C:/Program Files (x86)/LaserGRBL",
        license="GPL-3.0",
        capability_families=("LASER_CAM",),
        native_formats=(), import_formats=("NC", "G-code", "SVG", "DXF"),
        export_formats=("G-code",),
        cli=False, api=False, scripting=False, headless=False,
        bridge_adapter="",
        verification_status="INTERACTIVE_ONLY", last_verified="2026-10-07",
        limitations="Grbl controller GUI; no CLI found; NO hardware actuation permitted (simulation/prep only); shortcut healthy"))
    reg.register(ApplicationRecord(
        app_id="openmodelica", name="OpenModelica", version="1.27.1",
        executable="C:/Program Files/OpenModelica1.27.1-64bit/bin/omc.exe",
        install_path="C:/Program Files/OpenModelica1.27.1-64bit",
        license="OSMC-PL (EPL/GPL mix)",
        capability_families=("MECHATRONIC_SIMULATION", "CONTROL_SIMULATION"),
        native_formats=(".mo", ".mos", ".mat"),
        import_formats=(".mo",), export_formats=(".mat", ".csv", ".plt"),
        cli=True, api=True, scripting=True, headless=True,
        bridge_adapter="openmodelica_adapter.py",
        verification_status="VERIFIED", last_verified="2026-10-07",
        limitations="closure-proven 2026-10-07: direct omc decay sim (x(2)=0.1353, e^-2) + Agent Bridge chain supervisor->worker->openmodelica_adapter->omc->Decay_res.mat with transcript marker + numeric check (test_openmodelica_adapter.py, supervised-workers Path D); .mos scripts run with cwd=workdir; first compile ~31-117s so budgets stay >=600s"))
    # New 2026-10-07 discoveries: tools with no prior record at all.
    reg.register(ApplicationRecord(
        app_id="gimp", name="GIMP", version="3.2.6",
        executable="%LOCALAPPDATA%/Programs/GIMP 3/bin/gimp-3.2.exe",
        install_path="%LOCALAPPDATA%/Programs/GIMP 3",
        license="GPL-3.0+",
        capability_families=("RASTER_GRAPHICS", "IMAGE_PROCESSING", "BATCH_IMAGING"),
        native_formats=(".xcf",), import_formats=("PNG", "JPG", "TIFF", "PSD", "SVG"),
        export_formats=("PNG", "JPG", "TIFF", "WebP"),
        cli=True, api=True, scripting=True, headless=True,
        bridge_adapter="",
        verification_status="PARTIAL", last_verified="2026-10-07",
        limitations="installed 2026-10-07 from official download.gimp.org (3.2.6, user-scope, /CURRENTUSER, no UAC); first-run init + profile complete; gimp-console + plug-in-script-fu-eval + python-fu-eval interpreters proven (--batch-interpreter is MANDATORY in 3.x); script-fu PDB renamed (gimp-layer-new takes image LAST, procedural-db-proc-info gone); batch RENDER unproven; GUI launch deferred to owner"))
    reg.register(ApplicationRecord(
        app_id="godot", name="Godot", version="4.7.2-stable-mono",
        executable="%USERPROFILE%/Desktop/Programming & Code/Godot_v4.7.2-stable_mono_win64/Godot_v4.7.2-stable_mono_win64/Godot_v4.7.2-stable_mono_win64.exe",
        install_path="%USERPROFILE%/Desktop/Programming & Code/Godot_v4.7.2-stable_mono_win64",
        license="MIT",
        capability_families=("GAME_ENGINE", "INTERACTIVE_SIMULATION"),
        native_formats=(".tscn", ".godot"), import_formats=("glTF", "FBX", "OBJ"),
        export_formats=("EXE", "PCK"),
        cli=True, api=False, scripting=True, headless=True,
        bridge_adapter="",
        verification_status="PARTIAL", last_verified="2026-10-07",
        limitations="portable mono build, --version proven; Start Menu shortcut created 2026-10-07; headless project run/export untested (needs export templates); no bridge adapter yet"))
    reg.register(ApplicationRecord(
        app_id="arduino_ide", name="Arduino IDE", version="1.8.57.0 (Store pkg)",
        executable="(Store package ArduinoLLC.ArduinoIDE)",
        install_path="(MSIX package)",
        license="GPL-3.0 / LGPL (IDE 2.x core)",
        capability_families=("EMBEDDED_IDE", "FIRMWARE_UPLOAD"),
        native_formats=(".ino",), import_formats=(), export_formats=(".hex", ".bin"),
        cli=False, api=False, scripting=False, headless=False,
        bridge_adapter="",
        verification_status="INTERACTIVE_ONLY", last_verified="2026-10-07",
        limitations="Store GUI only, Start Menu shortcut copied 2026-10-07; use arduino_cli record for automation; NO board flashing without owner approval"))
    reg.register(ApplicationRecord(
        app_id="arduino_cli", name="Arduino CLI", version="1.5.2-rc.1",
        executable="%LOCALAPPDATA%/Programs/ArduinoCLI/arduino-cli.exe",
        install_path="%LOCALAPPDATA%/Programs/ArduinoCLI",
        license="GPL-3.0",
        capability_families=("EMBEDDED_TOOLCHAIN", "FIRMWARE_COMPILE"),
        native_formats=(), import_formats=(".ino",), export_formats=(".hex", ".bin"),
        cli=True, api=False, scripting=False, headless=True,
        bridge_adapter="",
        verification_status="PARTIAL", last_verified="2026-10-07",
        limitations="version proven; board cores NOT inventoried; compile/upload untested (upload needs owner approval + attached board); the automation path for Arduino work"))
    reg.register(ApplicationRecord(
        app_id="calculix", name="CalculiX", version="2.22",
        executable="%USERPROFILE%/AetheriusTools/calculix/calculix_2.22_4win/ccx_static.exe",
        install_path="%USERPROFILE%/AetheriusTools/calculix/calculix_2.22_4win",
        license="GPL-2.0",
        capability_families=("FEA", "STRUCTURAL_SIMULATION"),
        native_formats=(".inp", ".frd", ".dat"), import_formats=(".inp", ".msh"),
        export_formats=(".frd", ".dat", ".vtk"),
        cli=True, api=False, scripting=False, headless=True,
        bridge_adapter="",
        verification_status="PARTIAL", last_verified="2026-10-07",
        limitations="cantilever B31 proven 2026-10-07: 1-elem tip -0.144, 2-elem -0.1786, converging to EB theory -0.1905; also ships 2.20/2.21 + cgx + tetgen; .inp authoring is manual (FreeCAD FEM headless gap stands); no bridge adapter yet"))
    reg.register(ApplicationRecord(
        app_id="meshlab", name="MeshLab", version="2025.07",
        executable="C:/Program Files/VCG/MeshLab/meshlab.exe",
        install_path="C:/Program Files/VCG/MeshLab",
        license="GPL-3.0+",
        capability_families=("MESH_MODELING", "MESH_PROCESSING", "POINT_CLOUD"),
        native_formats=(".mlp", ".mlx"), import_formats=("STL", "OBJ", "PLY"),
        export_formats=("STL", "OBJ", "PLY"),
        cli=False, api=False, scripting=False, headless=False,
        bridge_adapter="",
        verification_status="INTERACTIVE_ONLY", last_verified="2026-10-07",
        limitations="meshlabserver removed upstream years ago: GUI only, no automation surface; filter work needs GUI .mlx authoring by owner"))
    reg.register(ApplicationRecord(
        app_id="krita", name="Krita", version="5.3.4",
        executable="C:/Program Files/Krita (x64)/bin/krita.exe",
        install_path="C:/Program Files/Krita (x64)",
        license="GPL-3.0+",
        capability_families=("RASTER_GRAPHICS", "DIGITAL_PAINTING"),
        native_formats=(".kra",), import_formats=("PNG", "JPG", "PSD", "SVG"),
        export_formats=("PNG", "JPG", "PSD"),
        cli=False, api=False, scripting=False, headless=False,
        bridge_adapter="",
        verification_status="INTERACTIVE_ONLY", last_verified="2026-10-07",
        limitations="installed + launched (GUI window confirmed, cleaned up); --version prints nothing headless; overlaps GIMP (raster) but distinct painting strengths; keep both"))
    # AI agent / orchestrator tooling measured 2026-10-07. VERIFIED stays
    # reserved for repo-adapter-wired tools; these are PARTIAL (real tests
    # executed, evidence recorded) or INTERACTIVE_ONLY (no automation found).
    reg.register(ApplicationRecord(
        app_id="hermes", name="Hermes Agent", version="0.21.3",
        executable="%LOCALAPPDATA%/hermes/bin/hermes.exe",
        install_path="%LOCALAPPDATA%/hermes/hermes-agent",
        license="(see hermes-agent LICENSE)",
        capability_families=("SUPERVISION", "ORCHESTRATION", "CODING_AGENT", "MCP_SERVER", "GATEWAY"),
        native_formats=(), import_formats=(), export_formats=(),
        cli=True, api=True, scripting=True, headless=True,
        bridge_adapter="",
        verification_status="PARTIAL", last_verified="2026-10-07",
        limitations="headless -z delegation PROVEN via new 'local' profile (Ollama ministral-3:3b, -t file, RESULT.txt verified); default Nous free model solar-pro4:free is DEAD (free period ended); needs ollama_num_ctx>=65536 + native-tool-call model (llama3.2/ministral ok; qwen/phi4-mini emit content-JSON); writes can escape --in dir (use absolute task paths); 10393 commits behind upstream (do NOT update mid-build); opencode.json already wires hermes MCP serve"))
    reg.register(ApplicationRecord(
        app_id="opencode", name="OpenCode", version="1.18.30",
        executable="%APPDATA%/npm/opencode (node)",
        install_path="%APPDATA%/npm/node_modules/opencode-ai",
        license="(see opencode-ai LICENSE)",
        capability_families=("SUPERVISION", "ORCHESTRATION", "CODING_AGENT", "ACP_SERVER", "MCP_CLIENT"),
        native_formats=(), import_formats=(), export_formats=(),
        cli=True, api=True, scripting=True, headless=True,
        bridge_adapter="",
        verification_status="PARTIAL", last_verified="2026-10-07",
        limitations="headless 'run -m ollama-local/qwen3:1.7b --dir' delegation PROVEN (RESULT2.txt verified, clean cwd scoping); provider is ollama-local with CURATED models only (qwen3:1.7b, qwen3.5:2b), NOT arbitrary ollama tags; 'serve'/'acp'/'mcp' surface present, untested"))
    reg.register(ApplicationRecord(
        app_id="openclaw", name="OpenClaw", version="2026.9.6 (node) / 2026.9.4 (Companion)",
        executable="%LOCALAPPDATA%/OpenClawTray (gateway distro: OpenClawGateway)",
        install_path="%LOCALAPPDATA%/OpenClawTray",
        license="(see OpenClaw LICENSE)",
        capability_families=("SUPERVISION", "ORCHESTRATION", "GATEWAY"),
        native_formats=(), import_formats=(), export_formats=(),
        cli=True, api=False, scripting=False, headless=False,
        bridge_adapter="",
        verification_status="PARTIAL", last_verified="2026-10-07",
        limitations="distro boots + CLI --version ok, but systemd user sessions broken (openclaw+root) and 'gateway' dies silently headless (no 18789 listener); wedged state cleared via wsl --terminate; restart REQUIRES owner via Companion GUI/tray (owns lifecycle+env); ws://127.0.0.1:18789 per setup-state"))
    reg.register(ApplicationRecord(
        app_id="codex", name="OpenAI Codex", version="0.155.1 (CLI) / 26.930.7945.0 (Store)",
        executable="%APPDATA%/npm/codex (node)",
        install_path="%APPDATA%/npm/node_modules/@openai/codex",
        license="commercial (OpenAI)",
        capability_families=("CODING_AGENT", "CODE_REVIEW"),
        native_formats=(), import_formats=(), export_formats=(),
        cli=True, api=True, scripting=True, headless=True,
        bridge_adapter="",
        verification_status="PARTIAL", last_verified="2026-10-07",
        limitations="CLI logged in via ChatGPT (no owner step needed); 'exec' non-interactive + mcp + app-server + doctor surface present, task execution untested; cost/vendor-dependent scoring pending"))
    reg.register(ApplicationRecord(
        app_id="cursor", name="Cursor", version="3.20.17",
        executable="%LOCALAPPDATA%/Programs/cursor/resources/app/bin/cursor.cmd",
        install_path="%LOCALAPPDATA%/Programs/cursor",
        license="commercial (Anysphere)",
        capability_families=("CODING_AGENT", "IDE"),
        native_formats=(), import_formats=(), export_formats=(),
        cli=True, api=False, scripting=False, headless=False,
        bridge_adapter="",
        verification_status="PARTIAL", last_verified="2026-10-07",
        limitations="Electron+cli.js --version proven (ELECTRON_RUN_AS_NODE); no headless task mode found; GUI IDE use deferred to owner"))
    reg.register(ApplicationRecord(
        app_id="ollama", name="Ollama", version="0.34.4",
        executable="%LOCALAPPDATA%/Programs/Ollama/ollama app.exe",
        install_path="%LOCALAPPDATA%/Programs/Ollama",
        license="SSPL (server) + MIT (client)",
        capability_families=("LOCAL_INFERENCE", "MODEL_RUNTIME", "EMBEDDINGS"),
        native_formats=(), import_formats=("GGUF",), export_formats=(),
        cli=True, api=True, scripting=True, headless=True,
        bridge_adapter="",
        verification_status="PARTIAL", last_verified="2026-10-07",
        limitations="daemon + 15-model fleet healthy (~30GB): qwen3/2.5-coder/deepseek-coder/ministral/phi4/granite/moondream/nomic-embed; inference proven (qwen3:0.6b READY-42); native tool_calls PROVEN for llama3.2:1b + ministral-3:3b, ABSENT for phi4-mini/qwen-coders (content-JSON); <=3B fits 4GB VRAM; runs at Startup"))
    reg.register(ApplicationRecord(
        app_id="lmstudio", name="LM Studio", version="0.4.25+1",
        executable="%LOCALAPPDATA%/Programs/LM Studio/LM Studio.exe",
        install_path="%USERPROFILE%/.lmstudio",
        license="commercial (LM Studio)",
        capability_families=("LOCAL_INFERENCE", "MODEL_RUNTIME"),
        native_formats=(), import_formats=("GGUF",), export_formats=(),
        cli=False, api=True, scripting=False, headless=False,
        bridge_adapter="",
        verification_status="PARTIAL", last_verified="2026-10-07",
        limitations="lms CLI 1.3.3 is INCOMPATIBLE: SIGILL 0xC000001D on every call (Bun binary needs AVX, i7-870 has none); GUI/server (:1234) untested, not running; Ollama covers the automation path"))
    for app_id, name, version, families in [
        ("manus", "Manus", "2.0.4.0 (Store)",
         ("CODING_AGENT", "BROWSER_AUTOMATION")),
        ("chatgpt", "ChatGPT", "(via OpenAI.Codex Store pkg)",
         ("CODING_AGENT", "RESEARCH")),
        ("copilot", "Copilot", "(Store)",
         ("CODING_AGENT", "IDE")),
    ]:
        reg.register(ApplicationRecord(
            app_id=app_id, name=name, version=version,
            executable="(Store app, no CLI on PATH)", install_path="(Store package)",
            license="commercial",
            capability_families=families,
            native_formats=(), import_formats=(), export_formats=(),
            cli=False, api=False, scripting=False, headless=False,
            bridge_adapter="",
            verification_status="INTERACTIVE_ONLY", last_verified="2026-10-07",
            limitations="installed; Start Menu shortcut present (created/copied 2026-10-07 where missing); no automation interface found"))
    return reg


APPLICATION_IDS = ("freecad", "blender", "cura", "kicad", "shapr3d",
                   "solvespace", "colmap", "gmsh", "orcaslicer",
                   "openscad", "librecad", "inkscape", "cloudcompare",
                   "camotics", "lasergrbl", "openmodelica",
                   "gimp", "godot", "arduino_ide", "arduino_cli",
                   "calculix", "meshlab", "krita",
                   "hermes", "opencode", "openclaw", "codex", "cursor",
                   "ollama", "lmstudio", "manus", "chatgpt", "copilot")
