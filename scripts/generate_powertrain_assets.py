"""Generates the eight `PowertrainExplainer` archetype assets (PHASE-6 SS5): one `.glb` cutaway
placeholder and one `.png` poster per archetype, under `web/public/models/powertrain/`.

Posters are plain PNG (not `.webp`, despite PHASE-6 SS5's own illustrative example) --
honestly reflects that this is a raw `zlib`-only PNG writer with no encoder for a real image
format's compressed variant, and the extension should say what the bytes actually are.

**Honest about what these are.** PHASE-6 SS5's own risk table calls for eight *real* cutaway
models -- licensed or hand-modelled geometry with real hotspot-worthy detail. Nobody on this
project has a 3D pipeline, so what ships here is a distinctly-coloured unit-cube glTF per
archetype: a real, valid, `<model-viewer>`-loadable GLB (hand-built to the glTF 2.0 binary
container spec, stdlib only -- no `pygltflib`/Pillow dependency for a placeholder this simple)
that proves the asset *pipeline* end to end -- discipline, poster fallback, size budget,
hotspot annotations -- without a single fabricated claim about what the geometry depicts. The
label CONSTITUTION I.5 requires ("representative image") is rendered in
`web/src/a2ui/catalog.tsx` regardless of which geometry sits behind it.

Swapping in real archetype models later is a file replacement under this same path and
filename convention, not a rewrite of anything that reads them.
"""

from __future__ import annotations

import json
import struct
import sys
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "web" / "public" / "models" / "powertrain"

#: PHASE-5/6's eight archetypes (src/domain/enums.py:PowertrainArchetype), each given a
#: distinct colour so the placeholder is at least visually distinguishable archetype to
#: archetype rather than eight identical grey cubes.
ARCHETYPES: dict[str, tuple[float, float, float]] = {
    "i3_turbo": (0.85, 0.35, 0.10),
    "i4_na": (0.20, 0.55, 0.85),
    "i4_turbo": (0.10, 0.35, 0.85),
    "v6": (0.60, 0.20, 0.70),
    "v8": (0.75, 0.10, 0.15),
    "hybrid": (0.15, 0.65, 0.30),
    "phev": (0.10, 0.75, 0.55),
    "bev_skateboard": (0.90, 0.85, 0.15),
}

MAX_MODEL_BYTES = 2 * 1024 * 1024  # gate 6.7
MAX_TOTAL_BYTES = 16 * 1024 * 1024  # gate 6.7

# -- a unit cube, indexed (glTF 2.0 core, no extensions) ---------------------------------------
_CUBE_POSITIONS: tuple[tuple[float, float, float], ...] = (
    (-0.5, -0.5, -0.5),
    (0.5, -0.5, -0.5),
    (0.5, 0.5, -0.5),
    (-0.5, 0.5, -0.5),
    (-0.5, -0.5, 0.5),
    (0.5, -0.5, 0.5),
    (0.5, 0.5, 0.5),
    (-0.5, 0.5, 0.5),
)
# back, front, bottom, top, right, left -- two triangles per face, 6*6 = 36 indices.
_CUBE_INDICES: tuple[int, ...] = (
    0, 1, 2, 2, 3, 0,
    4, 6, 5, 6, 4, 7,
    0, 4, 5, 5, 1, 0,
    3, 2, 6, 6, 7, 3,
    1, 5, 6, 6, 2, 1,
    4, 0, 3, 3, 7, 4,
)  # fmt: skip


def _pad(data: bytes, boundary: int, fill: bytes) -> bytes:
    remainder = len(data) % boundary
    if remainder == 0:
        return data
    return data + fill * (boundary - remainder)


def build_glb(color: tuple[float, float, float]) -> bytes:
    position_bytes = b"".join(struct.pack("<3f", *v) for v in _CUBE_POSITIONS)
    index_bytes = b"".join(struct.pack("<H", i) for i in _CUBE_INDICES)
    binary_chunk = position_bytes + index_bytes
    assert len(binary_chunk) % 4 == 0, "8 vertices + 36 uint16 indices is already 4-byte aligned"

    xs = [v[0] for v in _CUBE_POSITIONS]
    ys = [v[1] for v in _CUBE_POSITIONS]
    zs = [v[2] for v in _CUBE_POSITIONS]

    gltf: dict[str, object] = {
        "asset": {"version": "2.0", "generator": "cardinal/scripts/generate_powertrain_assets.py"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}],
        "materials": [
            {
                "name": "archetype-color",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [*color, 1.0],
                    "metallicFactor": 0.3,
                    "roughnessFactor": 0.6,
                },
            }
        ],
        "buffers": [{"byteLength": len(binary_chunk)}],
        "bufferViews": [
            {
                "buffer": 0,
                "byteOffset": 0,
                "byteLength": len(position_bytes),
                "target": 34962,  # ARRAY_BUFFER
            },
            {
                "buffer": 0,
                "byteOffset": len(position_bytes),
                "byteLength": len(index_bytes),
                "target": 34963,  # ELEMENT_ARRAY_BUFFER
            },
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,  # FLOAT
                "count": len(_CUBE_POSITIONS),
                "type": "VEC3",
                "min": [min(xs), min(ys), min(zs)],
                "max": [max(xs), max(ys), max(zs)],
            },
            {
                "bufferView": 1,
                "componentType": 5123,  # UNSIGNED_SHORT
                "count": len(_CUBE_INDICES),
                "type": "SCALAR",
            },
        ],
    }

    json_chunk = _pad(json.dumps(gltf, separators=(",", ":")).encode("utf-8"), 4, b" ")

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        return struct.pack("<II", len(data), int.from_bytes(chunk_type, "little")) + data

    body = chunk(b"JSON", json_chunk) + chunk(b"BIN\x00", binary_chunk)
    header = struct.pack("<III", 0x46546C67, 2, 12 + len(body))
    return header + body


# -- a minimal solid-colour PNG poster, stdlib zlib only (no Pillow) ----------------------------


def build_poster_png(color: tuple[float, float, float], size: int = 128) -> bytes:
    r, g, b = (round(c * 255) for c in color)
    raw = bytearray()
    for _ in range(size):
        raw.append(0)  # filter type 0 (None) per scanline
        raw.extend((r, g, b) * size)

    def png_chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit truecolor (RGB)
    idat = zlib.compress(bytes(raw), level=9)
    return signature + png_chunk(b"IHDR", ihdr) + png_chunk(b"IDAT", idat) + png_chunk(b"IEND", b"")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    for archetype, color in ARCHETYPES.items():
        glb = build_glb(color)
        poster = build_poster_png(color)
        glb_path = OUT_DIR / f"{archetype}.glb"
        poster_path = OUT_DIR / f"{archetype}.png"
        glb_path.write_bytes(glb)
        poster_path.write_bytes(poster)
        total_bytes += len(glb) + len(poster)
        assert len(glb) <= MAX_MODEL_BYTES, f"{archetype}.glb is {len(glb)} bytes, over budget"
        print(
            f"wrote {glb_path.relative_to(REPO_ROOT)} ({len(glb)} bytes) "
            f"+ poster ({len(poster)} bytes)"
        )

    assert total_bytes <= MAX_TOTAL_BYTES, f"total asset bundle {total_bytes} bytes over budget"
    print(f"total asset bundle: {total_bytes} bytes (budget {MAX_TOTAL_BYTES})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
