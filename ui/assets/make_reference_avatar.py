"""Generate the procedural reference avatar (one-shot, committed output).

Builds a minimal valid glTF 2.0 binary (.glb): a neutral box humanoid with
named nodes (Head/Jaw/EyeL/EyeR/...) so lip-sync and gaze have targets.
No downloaded assets, no copyrighted models. Users may load any VRM/GLB.
"""
import json
import struct

BOX_FACES = [
    # (corners of unit cube), wound outward
    ((0, 1, 3, 2), (0, 0, 1)),   # front
    ((5, 4, 6, 7), (0, 0, -1)),  # back
    ((4, 0, 2, 6), (-1, 0, 0)),  # left
    ((1, 5, 7, 3), (1, 0, 0)),   # right
    ((4, 5, 1, 0), (0, -1, 0)),  # bottom
    ((2, 3, 7, 6), (0, 1, 0)),   # top
]
CORNERS = [(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (-0.5, 0.5, -0.5),
           (0.5, 0.5, -0.5), (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5),
           (-0.5, 0.5, 0.5), (0.5, 0.5, 0.5)]

# name -> (center xyz, size xyz)
PARTS = {
    "Hips": ((0.0, 0.95, 0.0), (0.34, 0.18, 0.2)),
    "Torso": ((0.0, 1.25, 0.0), (0.4, 0.42, 0.22)),
    "Head": ((0.0, 1.68, 0.0), (0.26, 0.3, 0.26)),
    "Jaw": ((0.0, 1.58, 0.1), (0.16, 0.08, 0.1)),
    "EyeL": ((-0.07, 1.7, 0.12), (0.05, 0.05, 0.03)),
    "EyeR": ((0.07, 1.7, 0.12), (0.05, 0.05, 0.03)),
    "ArmL": ((-0.28, 1.25, 0.0), (0.12, 0.44, 0.14)),
    "ArmR": ((0.28, 1.25, 0.0), (0.12, 0.44, 0.14)),
    "LegL": ((-0.11, 0.45, 0.0), (0.15, 0.72, 0.17)),
    "LegR": ((0.11, 0.45, 0.0), (0.15, 0.72, 0.17)),
}


def box_geometry(center, size):
    positions, normals, indices = [], [], []
    base = 0
    for corners, normal in BOX_FACES:
        for ci in corners:
            cx, cy, cz = CORNERS[ci]
            positions.append((center[0] + cx * size[0],
                              center[1] + cy * size[1],
                              center[2] + cz * size[2]))
            normals.append(normal)
        a, b, c, d = base, base + 1, base + 2, base + 3
        indices += [a, b, c, a, c, d]
        base += 4
    return positions, normals, indices


def main():
    blob = bytearray()
    accessors, views, meshes, nodes = [], [], [], []
    for name, (center, size) in PARTS.items():
        pos, nor, idx = box_geometry(center, size)
        for data, comp, ctype in ((pos, "VEC3", "FLOAT"), (nor, "VEC3", "FLOAT"),
                                  (idx, "SCALAR", "UNSIGNED_SHORT")):
            flat = [v for p in data for v in (p if isinstance(p, tuple) else (p,))]
            fmt = "<" + ("f" * len(flat) if ctype == "FLOAT" else "H" * len(flat))
            raw = struct.pack(fmt, *flat)
            while len(blob) % 4:
                blob.append(0)
            views.append({"buffer": 0, "byteOffset": len(blob),
                          "byteLength": len(raw)})
            blob.extend(raw)
            mn = [min(p[i] for p in data) for i in range(len(data[0]) if isinstance(data[0], tuple) else 1)] if ctype == "FLOAT" and comp == "VEC3" else None
            accessors.append({"bufferView": len(views) - 1, "componentType": 5126 if ctype == "FLOAT" else 5123,
                              "count": len(data), "type": comp,
                              **({"min": mn, "max": [max(p[i] for p in data) for i in range(3)]} if mn else {})})
        n = len(accessors)
        meshes.append({"name": name, "primitives": [
            {"attributes": {"POSITION": n - 3, "NORMAL": n - 2},
             "indices": n - 1}]})
        nodes.append({"name": name, "mesh": len(meshes) - 1})
    gltf = {"asset": {"version": "2.0",
                      "generator": "agent-bridge reference avatar (procedural, no external assets)"},
            "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}],
            "nodes": nodes, "meshes": meshes,
            "accessors": accessors, "bufferViews": views,
            "buffers": [{"byteLength": len(blob)}],
            "extras": {"agentBridge": {"avatar": "reference-humanoid",
                                       "lipSyncTargets": ["Jaw"],
                                       "gazeTargets": ["EyeL", "EyeR"]}}}
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode()
    while len(json_bytes) % 4:
        json_bytes += b" "
    total = 12 + 8 + len(json_bytes) + 8 + len(blob)
    out = struct.pack("<III", 0x46546C67, 2, total)
    out += struct.pack("<II", len(json_bytes), 0x4E4F534A) + json_bytes
    out += struct.pack("<II", len(blob), 0x004E4942) + bytes(blob)
    with open("reference-avatar.glb", "wb") as f:
        f.write(out)
    print("wrote reference-avatar.glb", len(out), "bytes,", len(nodes), "nodes")


if __name__ == "__main__":
    raise SystemExit(main())
