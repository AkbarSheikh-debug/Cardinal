"""D-060: resolving a listing to the 3D asset that stands for it, and the enriched
`compile_results_surface` that puts it on a card.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.adapters.catalogue.generator import generate_catalogue
from src.adapters.catalogue.taxonomy import MODELS_BY_CATEGORY
from src.adapters.store import InMemoryListingStore
from src.domain.enums import Currency, OfferType, VehicleCategory
from src.domain.marketplace import SearchQuery
from src.domain.money import Money
from src.mcp.ui.compiler import CardVisual, compile_results_surface
from src.mcp.ui.vehicle_models import (
    SILHOUETTE_DIR,
    VEHICLE_DIR,
    VEHICLE_SLUGS,
    is_representative,
    slugify,
    vehicle_model_src,
    vehicle_poster_src,
)


def _eur(amount: int) -> Money:
    return Money(amount=Decimal(amount), currency=Currency.EUR)


#: The structured search each prompt in `docs/DEMO-SCRIPT.md` resolves to once the interview
#: has filled the profile. `page_size=4` because that is how many cards the script shows.
#: These are the queries `VEHICLE_SLUGS` was derived from -- change one and re-derive.
DEMO_SCRIPT_QUERIES: tuple[SearchQuery, ...] = (
    # A -- family SUV to buy
    SearchQuery(
        categories=(VehicleCategory.SUV,),
        offer_type=OfferType.BUY,
        max_price=_eur(30_000),
        min_year=2020,
        page_size=4,
    ),
    # B -- cheapest thing that runs
    SearchQuery(
        categories=(VehicleCategory.HATCHBACK,),
        offer_type=OfferType.BUY,
        max_price=_eur(13_000),
        page_size=4,
    ),
    # C -- first EV
    SearchQuery(
        categories=(VehicleCategory.ELECTRIC,),
        offer_type=OfferType.BUY,
        max_price=_eur(25_000),
        page_size=4,
    ),
    # D -- commuter sedan
    SearchQuery(
        categories=(VehicleCategory.SEDAN,),
        offer_type=OfferType.BUY,
        max_price=_eur(20_000),
        min_year=2018,
        page_size=4,
    ),
    # E -- crossover on a tight budget
    SearchQuery(
        categories=(VehicleCategory.CROSSOVER,),
        offer_type=OfferType.BUY,
        max_price=_eur(18_000),
        page_size=4,
    ),
    # F -- SUV rental (the rent-vs-buy branch)
    SearchQuery(
        categories=(VehicleCategory.SUV,),
        offer_type=OfferType.RENT,
        max_rental_daily=_eur(60),
        page_size=4,
    ),
    # G -- estate for the dog and the boot space
    SearchQuery(
        categories=(VehicleCategory.WAGON,),
        offer_type=OfferType.BUY,
        max_price=_eur(30_000),
        min_year=2020,
        page_size=4,
    ),
    # H -- weekend sports rental
    SearchQuery(
        categories=(VehicleCategory.SPORTS,),
        offer_type=OfferType.RENT,
        max_rental_daily=_eur(140),
        page_size=4,
    ),
)


@pytest.mark.parametrize(
    ("brand", "model", "expected"),
    [
        ("Toyota", "RAV4", "toyota-rav4"),
        ("Mercedes-Benz", "C-Class", "mercedes-benz-c-class"),
        ("VW", "ID.4", "vw-id-4"),
        ("Peugeot", "e-208", "peugeot-e-208"),
        ("BMW", "3 Series Touring", "bmw-3-series-touring"),
        # The catalogue's spellings are genuinely accented (PHASE-1's taxonomy is deliberately
        # accurate); a downloaded file will not be.
        ("Škoda", "Octavia", "skoda-octavia"),
        ("Renault", "Mégane Estate", "renault-megane-estate"),
    ],
)
def test_slugify_folds_to_a_filename_someone_would_actually_save(
    brand: str, model: str, expected: str
) -> None:
    assert slugify(brand, model) == expected


def test_every_declared_slug_names_a_car_the_catalogue_can_actually_offer() -> None:
    """A slug with no listing behind it is a GLB nobody will ever see -- and, more usefully,
    catches a typo in `VEHICLE_SLUGS` that would otherwise only show up as a silent fallback.
    """
    known = {slugify(s.brand, s.model) for specs in MODELS_BY_CATEGORY.values() for s in specs}
    assert VEHICLE_SLUGS <= known, sorted(VEHICLE_SLUGS - known)


def test_sourced_car_resolves_to_its_own_model() -> None:
    src = vehicle_model_src("Nissan", "GT-R", VehicleCategory.SPORTS)
    assert src == f"{VEHICLE_DIR}/nissan-gt-r.glb"
    assert vehicle_poster_src("Nissan", "GT-R", VehicleCategory.SPORTS) == (
        f"{VEHICLE_DIR}/nissan-gt-r.png"
    )
    assert is_representative("Nissan", "GT-R") is False


def test_unsourced_car_falls_back_to_its_body_style() -> None:
    # Real catalogue entry (PHASE-1 taxonomy), deliberately not in VEHICLE_SLUGS.
    src = vehicle_model_src("Tata", "Yodha", VehicleCategory.PICKUP)
    assert src == f"{SILHOUETTE_DIR}/pickup.glb"
    assert is_representative("Tata", "Yodha") is True


@pytest.mark.parametrize("category", list(VehicleCategory))
def test_every_category_resolves_for_a_car_nobody_sourced(category: VehicleCategory) -> None:
    """There is no "no model" case: the renderer never has to branch on a missing asset."""
    src = vehicle_model_src("Nonexistent", "Whatever", category)
    assert src == f"{SILHOUETTE_DIR}/{category.value}.glb"
    assert src.endswith(".glb")


async def test_every_car_the_demo_script_surfaces_has_its_own_model() -> None:
    """`docs/DEMO-SCRIPT.md` promises that a scripted run shows the actual car on every card.
    `VEHICLE_SLUGS` was derived from these very queries, so this is the test that keeps the
    promise honest when the seed, the catalogue, or the slug set changes -- without it, a
    regression degrades silently into body-style silhouettes and nothing fails.
    """
    store = InMemoryListingStore(generate_catalogue())
    sources = ("mock_autobazaar", "mock_drivenow")

    fell_back: list[str] = []
    for query in DEMO_SCRIPT_QUERIES:
        listings, _ = await store.query(query, sources=sources)
        fell_back += [
            f"{listing.brand} {listing.model}"
            for listing in listings
            if is_representative(listing.brand, listing.model)
        ]

    assert not fell_back, f"demo cards falling back to a silhouette: {sorted(set(fell_back))}"


def _args() -> dict[str, object]:
    return {
        "weights": {"budget_fit": 1.0},
        "items": [
            {
                "source": "mock_autobazaar",
                "source_id": "AB-1",
                "rank": 1,
                "score": 0.9,
                "rationale": "cheapest that fits",
            },
            {
                "source": "mock_drivenow",
                "source_id": "DN-2",
                "rank": 2,
                "score": 0.7,
                "rationale": "available sooner",
            },
        ],
    }


def test_results_surface_without_visuals_is_unchanged() -> None:
    """The pre-D-060 shape still compiles -- a caller with no store wired up degrades to a
    text card rather than to an error.
    """
    compiled = compile_results_surface(_args())
    cards = [c for c in compiled.components if c["component"] == "CarCard"]
    assert len(cards) == 2
    for card in cards:
        assert "modelSrc" not in card
        assert "posterSrc" not in card


def test_results_surface_puts_the_resolved_asset_on_the_matching_card_only() -> None:
    visuals = {
        ("mock_autobazaar", "AB-1"): CardVisual(
            headline="2021 Porsche 911",
            model_src=f"{VEHICLE_DIR}/porsche-911.glb",
            poster_src=f"{VEHICLE_DIR}/porsche-911.png",
            representative=False,
        )
    }
    compiled = compile_results_surface(_args(), visuals=visuals)
    by_id = {c["id"]: c for c in compiled.components if c["component"] == "CarCard"}

    assert by_id["card-0"]["modelSrc"] == f"{VEHICLE_DIR}/porsche-911.glb"
    assert by_id["card-0"]["headline"] == "2021 Porsche 911"
    assert by_id["card-0"]["representative"] is False
    # The listing with no entry keeps the text-only shape rather than borrowing its neighbour's.
    assert "modelSrc" not in by_id["card-1"]
