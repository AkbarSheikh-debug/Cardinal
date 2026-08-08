"""Reconciles `vehicle_models.VEHICLE_SLUGS` against what is actually on disk under
`web/public/models/` (D-060), and re-checks gate 6.7's size budget over the whole bundle.

`src/mcp/ui/vehicle_models.py` is a pure lookup table with no filesystem access on purpose --
a compiler that stats the disk stops being the pure function PHASE-6 SS4 requires. This script
is where the two are allowed to meet. Run it after dropping new GLBs in:

    python -m scripts.check_vehicle_assets

Exit code is 0 when every declared slug has both files and nothing is over budget, 1 otherwise.
`--missing-ok` downgrades absent per-vehicle models to a warning, which is the honest setting
while the set is still being sourced: an unsourced car falls back to its body-style silhouette
at runtime rather than breaking, so a missing file is a gap in polish, not a broken build.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.domain.enums import VehicleCategory
from src.mcp.ui.vehicle_models import VEHICLE_SLUGS

REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_ROOT = REPO_ROOT / "web" / "public" / "models"
VEHICLE_DIR = MODELS_ROOT / "vehicles"
SILHOUETTE_DIR = MODELS_ROOT / "silhouettes"
POWERTRAIN_DIR = MODELS_ROOT / "powertrain"

MAX_MODEL_BYTES = 2 * 1024 * 1024  # gate 6.7
MAX_TOTAL_BYTES = 16 * 1024 * 1024  # gate 6.7


def _pair_status(directory: Path, stem: str) -> tuple[bool, int]:
    """`(both files present, bytes on disk)` for one `<stem>.glb` + `<stem>.png` pair."""
    glb, png = directory / f"{stem}.glb", directory / f"{stem}.png"
    size = (glb.stat().st_size if glb.exists() else 0) + (png.stat().st_size if png.exists() else 0)
    return glb.exists() and png.exists(), size


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--missing-ok",
        action="store_true",
        help="absent per-vehicle models warn instead of failing (they fall back at runtime)",
    )
    args = parser.parse_args(argv)

    failed = False
    total = 0
    oversized: list[str] = []

    def audit(label: str, directory: Path, stems: list[str], required: bool) -> list[str]:
        nonlocal failed, total
        absent: list[str] = []
        for stem in sorted(stems):
            present, size = _pair_status(directory, stem)
            total += size
            if not present:
                absent.append(stem)
                if required:
                    failed = True
                continue
            glb_bytes = (directory / f"{stem}.glb").stat().st_size
            if glb_bytes > MAX_MODEL_BYTES:
                oversized.append(f"{label}/{stem}.glb ({glb_bytes:,} bytes)")
                failed = True
        return absent

    # The two fallback tiers are required: every listing resolves to one of them, so a gap
    # here is a card that renders nothing at all.
    missing_powertrain = audit(
        "powertrain", POWERTRAIN_DIR, [p.stem for p in POWERTRAIN_DIR.glob("*.glb")], True
    )
    missing_silhouettes = audit(
        "silhouettes", SILHOUETTE_DIR, [c.value for c in VehicleCategory], True
    )
    # Per-vehicle models are the polish tier -- absent ones fall back to a silhouette.
    missing_vehicles = audit("vehicles", VEHICLE_DIR, sorted(VEHICLE_SLUGS), not args.missing_ok)

    print(f"declared per-vehicle slugs : {len(VEHICLE_SLUGS)}")
    print(f"present                    : {len(VEHICLE_SLUGS) - len(missing_vehicles)}")
    print(
        f"body-style silhouettes     : {len(VehicleCategory) - len(missing_silhouettes)}"
        f"/{len(VehicleCategory)}"
    )
    print(f"total asset bundle         : {total:,} bytes (budget {MAX_TOTAL_BYTES:,})")

    if total > MAX_TOTAL_BYTES:
        print(f"\nFAIL: bundle is {total - MAX_TOTAL_BYTES:,} bytes over gate 6.7's budget.")
        print("      Decimate meshes and Draco-compress, or cut slugs from VEHICLE_SLUGS.")
        failed = True
    if oversized:
        print("\nFAIL: over the 2 MB per-model cap:")
        for entry in oversized:
            print(f"  {entry}")
    if missing_silhouettes:
        print("\nFAIL: missing body-style silhouettes (run scripts/generate_silhouette_assets.py):")
        for stem in missing_silhouettes:
            print(f"  silhouettes/{stem}.{{glb,png}}")
    if missing_powertrain:
        print("\nFAIL: missing powertrain archetypes (run scripts/generate_powertrain_assets.py):")
        for stem in missing_powertrain:
            print(f"  powertrain/{stem}.{{glb,png}}")
    if missing_vehicles:
        verb = "still to source" if args.missing_ok else "MISSING"
        print(f"\n{verb} -- these fall back to their body-style silhouette at runtime:")
        for stem in missing_vehicles:
            print(f"  vehicles/{stem}.{{glb,png}}")

    if failed:
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
