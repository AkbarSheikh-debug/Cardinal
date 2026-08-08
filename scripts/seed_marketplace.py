"""Seed the marketplace catalogue into Postgres (PHASE-1 §4).

Idempotent by natural key: re-running upserts on `(source, source_id)` rather than
duplicating, which is what lets the compose `command` seed unconditionally on every start.

    python -m scripts.seed_marketplace                 # upsert the default 240
    python -m scripts.seed_marketplace --if-empty      # skip when rows already exist
    python -m scripts.seed_marketplace --dump out.json # no database; used by gate 1.6
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from src.adapters.catalogue.generator import DEFAULT_SEED, DEFAULT_TOTAL, generate_catalogue
from src.adapters.db.mapping import to_row
from src.adapters.db.models import ListingRow
from src.adapters.db.session import (
    dispose_engine,
    resolved_database_url,
    run_async,
    session_factory,
)
from src.domain.listing import Listing

#: Columns refreshed on conflict. `id` and the natural key are excluded -- they are the
#: conflict target, not payload.
_MUTABLE_COLUMNS = tuple(
    column.name
    for column in ListingRow.__table__.columns
    if column.name not in {"id", "source", "source_id"}
)


def catalogue_as_json(seed: int = DEFAULT_SEED, total: int = DEFAULT_TOTAL) -> str:
    """A stable JSON rendering of the whole catalogue.

    Gate 1.6 hashes this from two separate processes. `sort_keys` plus a fixed separator
    means the comparison tests the generator's determinism rather than dict ordering.
    """
    listings = generate_catalogue(seed=seed, total=total)
    payload = [listing.model_dump(mode="json") for listing in listings]
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False)


async def seed(
    *, seed_value: int, total: int, if_empty: bool, verbose: bool = True
) -> tuple[int, bool]:
    """Returns `(rows_in_table, did_write)`."""
    sessions = session_factory()
    listings: tuple[Listing, ...] = generate_catalogue(seed=seed_value, total=total)

    async with sessions() as session:
        existing = int(await session.scalar(select(func.count()).select_from(ListingRow)) or 0)
        if if_empty and existing:
            if verbose:
                print(f"listings table already has {existing} rows; --if-empty, nothing to do")
            return existing, False

        for listing in listings:
            row = to_row(listing)
            values = {
                column.name: getattr(row, column.name) for column in ListingRow.__table__.columns
            }
            stmt = insert(ListingRow).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[ListingRow.source, ListingRow.source_id],
                set_={name: stmt.excluded[name] for name in _MUTABLE_COLUMNS},
            )
            await session.execute(stmt)
        await session.commit()

        final = int(await session.scalar(select(func.count()).select_from(ListingRow)) or 0)

    if verbose:
        print(f"seeded {len(listings)} listings (seed={seed_value}); table now holds {final}")
    return final, True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--total", type=int, default=DEFAULT_TOTAL)
    parser.add_argument(
        "--if-empty", action="store_true", help="do nothing when the table already has rows"
    )
    parser.add_argument(
        "--dump",
        type=Path,
        help="write the generated catalogue to a JSON file and exit; touches no database",
    )
    args = parser.parse_args(argv)

    if args.dump is not None:
        args.dump.parent.mkdir(parents=True, exist_ok=True)
        args.dump.write_text(catalogue_as_json(args.seed, args.total), encoding="utf-8")
        print(f"wrote {args.total} listings to {args.dump}")
        return 0

    print(f"seeding against {resolved_database_url().rsplit('@', 1)[-1]}")

    async def run() -> None:
        try:
            await seed(seed_value=args.seed, total=args.total, if_empty=args.if_empty)
        finally:
            await dispose_engine()

    run_async(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
