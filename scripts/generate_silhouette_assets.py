"""Generates the twelve body-style silhouette placeholders (D-060): one `.glb` + one `.png`
poster per `VehicleCategory`, under `web/public/models/silhouettes/`.

This is `src/mcp/ui/vehicle_models.py`'s middle fallback -- what a `CarCard` shows when the
catalogue's listing is a car nobody has sourced a per-vehicle model for. There are 146 distinct
`(brand, model)` pairs in the seeded catalogue and a 16 MB total asset budget (gate 6.7), so
covering every one of them was never on the table; twelve body styles mean every card renders
*something* with roughly the right proportions instead of a hole.

**Honest about what these are**, exactly as `generate_powertrain_assets.py` is: a
distinctly-coloured unit cube per category, not a modelled body shell. It proves the pipeline
-- resolution, poster fallback, size budget, the "body style shown for reference" label -- and
makes swapping in real geometry a file replacement under the same path convention, not a code
change. Replace these before anyone calls the 3D view finished; a cube is not a silhouette.

Real per-vehicle models go in `web/public/models/vehicles/<slug>.glb` instead, and their slugs
are listed in `vehicle_models.VEHICLE_SLUGS`. `scripts/check_vehicle_assets.py` reports which
of those are still missing.
"""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.generate_powertrain_assets import (
    MAX_MODEL_BYTES,
    MAX_TOTAL_BYTES,
    build_glb,
    build_poster_png,
)
from src.domain.enums import VehicleCategory

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "web" / "public" / "models" / "silhouettes"

#: One colour per body style, distinct from each other so twelve placeholders are at least
#: tellable apart on screen. Warm for the small/cheap end, cool for the large/expensive end --
#: no meaning is claimed beyond "these are different categories".
CATEGORY_COLORS: dict[VehicleCategory, tuple[float, float, float]] = {
    VehicleCategory.HATCHBACK: (0.95, 0.65, 0.20),
    VehicleCategory.SEDAN: (0.85, 0.45, 0.25),
    VehicleCategory.CROSSOVER: (0.70, 0.55, 0.30),
    VehicleCategory.SUV: (0.45, 0.55, 0.35),
    VehicleCategory.WAGON: (0.35, 0.60, 0.50),
    VehicleCategory.VAN_MPV: (0.30, 0.55, 0.65),
    VehicleCategory.PICKUP: (0.50, 0.40, 0.30),
    VehicleCategory.COUPE: (0.60, 0.30, 0.55),
    VehicleCategory.CONVERTIBLE: (0.75, 0.35, 0.60),
    VehicleCategory.SPORTS: (0.80, 0.20, 0.25),
    VehicleCategory.LUXURY: (0.35, 0.35, 0.60),
    VehicleCategory.ELECTRIC: (0.25, 0.70, 0.60),
}


def main() -> int:
    missing = set(VehicleCategory) - set(CATEGORY_COLORS)
    if missing:
        print(f"no colour for {sorted(c.value for c in missing)}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    for category, color in CATEGORY_COLORS.items():
        glb = build_glb(color)
        poster = build_poster_png(color)
        glb_path = OUT_DIR / f"{category.value}.glb"
        poster_path = OUT_DIR / f"{category.value}.png"
        glb_path.write_bytes(glb)
        poster_path.write_bytes(poster)
        total_bytes += len(glb) + len(poster)
        if len(glb) > MAX_MODEL_BYTES:
            print(f"{category.value}.glb is {len(glb)} bytes, over budget", file=sys.stderr)
            return 1
        print(
            f"wrote {glb_path.relative_to(REPO_ROOT)} ({len(glb)} bytes) "
            f"+ poster ({len(poster)} bytes)"
        )

    print(f"silhouette bundle: {total_bytes} bytes (whole-bundle budget {MAX_TOTAL_BYTES})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
