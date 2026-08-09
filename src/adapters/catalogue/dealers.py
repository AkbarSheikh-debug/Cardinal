"""The deterministic synthetic dealer directory (PLAN-02 P13, PLAN-01 §0 decision 1).

Extends `generator.py`'s pattern one table over: seeded, reproducible, byte-identical across
two runs (gate 13.2, the same discipline gate 1.6 enforces for the catalogue). Nothing here
reads the clock, a network, or a real dealer-locator page.

**Why synthetic and not scraped, even for the demo.** Scraping a real "Find a Dealer" page and
swapping in fictional contact details still means the *request* happened without a ToS check,
and relabelled real-dealer structure with invented phone numbers reads as impersonation of a
real business if anyone looks closely. A live scraper stays `[SCALE]`, gated on legal review.
This generator is not a placeholder for it -- it is the permanent demo and dev data source.

**Why the names are checked against a denylist.** Generating from parts is not by itself
enough to guarantee a name doesn't collide with a real business: "Suzuki Motors Berlin" is a
perfectly reachable output of a naive combiner over a pool that contains real brand names.
`assert_no_real_world_collisions` is the check that makes "fictional" an assertion (gate 13.3)
rather than an intention.
"""

from __future__ import annotations

import random
from decimal import Decimal

from src.adapters.catalogue.taxonomy import CITIES, all_brands
from src.domain.dealer import Dealer, VerificationStatus, dealer_uuid

#: How many dealers each marketplace carries in each city. Three is enough that a city's
#: listings spread across more than one business (so "which dealer has it" is a real question
#: in the demo) without inflating the directory past what 240 listings can populate.
DEALERS_PER_CITY = 3

#: Invented, geography-flavoured first words. Checked against the brand pool by
#: `assert_no_real_world_collisions`, not merely eyeballed.
_PREFIXES: tuple[str, ...] = (
    "Nordkap",
    "Vierbrug",
    "Altstadt",
    "Kanaalzicht",
    "Hafenblick",
    "Steenweg",
    "Lindenhof",
    "Marktplein",
    "Ringstraat",
    "Zuidpoort",
    "Ostkreuz",
    "Vieuxpont",
)

_CORES: tuple[str, ...] = (
    "Automobile",
    "Motors",
    "Fahrzeuge",
    "Auto Centrum",
    "Carworks",
    "Mobility",
    "Autohaus",
    "Vehicles",
)

#: Legal forms by country, so a Munich dealer is a GmbH and a Rotterdam one a B.V. Cosmetic,
#: but a directory where every entry is "Ltd" reads as generated at a glance -- and the whole
#: value of dealer attribution is that a buyer believes there is a real business there.
_LEGAL_FORM: dict[str, str] = {
    "DE": "GmbH",
    "NL": "B.V.",
    "BE": "BVBA",
    "FR": "SARL",
    "AT": "GmbH",
    "CH": "AG",
    "CZ": "s.r.o.",
    "PL": "Sp. z o.o.",
    "IT": "S.r.l.",
    "ES": "S.L.",
    "PT": "Lda.",
    "IE": "Ltd",
    "DK": "ApS",
    "SE": "AB",
}

#: Street names by language group, so a Berlin dealer sits on a `Gewerbestrasse` and a Milan
#: one on a `Via Artigiani`. Drawing from one flat pool put "Via Artigiani 64, Berlin" in the
#: directory on the first run -- two facts on one line that contradict each other, which is
#: exactly the tell that makes a buyer stop believing the dealer is real.
_STREETS_BY_COUNTRY: dict[str, tuple[str, ...]] = {
    "DE": ("Gewerbestrasse", "Werkstattallee", "Industriestrasse", "Autohofweg"),
    "AT": ("Gewerbestrasse", "Werkstattallee", "Industriestrasse"),
    "CH": ("Gewerbestrasse", "Industriestrasse", "Werkhofweg"),
    "NL": ("Industrieweg", "Handelskade", "Havenlaan", "Werkplaatsstraat"),
    "BE": ("Industrieweg", "Havenlaan", "Nijverheidslaan"),
    "FR": ("Rue du Commerce", "Avenue des Ateliers", "Boulevard Industriel"),
    "IT": ("Via Artigiani", "Via dell'Industria", "Viale delle Officine"),
    "ES": ("Polígono Norte", "Calle del Taller", "Avenida Industrial"),
    "PT": ("Rua da Indústria", "Avenida das Oficinas"),
    "CZ": ("Průmyslová", "Dílenská", "Obchodní"),
    "PL": ("Przemysłowa", "Warsztatowa", "Handlowa"),
    "DK": ("Industrivej", "Værkstedsvej"),
    "SE": ("Industrigatan", "Verkstadsvägen"),
    "IE": ("Industrial Estate Road", "Forge Lane", "Commerce Park"),
}

#: International dialling prefixes, so a phone number at least looks like it belongs to the
#: city it is printed under.
_DIAL_CODE: dict[str, str] = {
    "DE": "+49",
    "NL": "+31",
    "BE": "+32",
    "FR": "+33",
    "AT": "+43",
    "CH": "+41",
    "CZ": "+420",
    "PL": "+48",
    "IT": "+39",
    "ES": "+34",
    "PT": "+351",
    "IE": "+353",
    "DK": "+45",
    "SE": "+46",
}

#: Weighted so most dealers are verified but the unverified path is genuinely populated --
#: P14's checkout has to render its "payee identity unverified" flag against real data, and a
#: directory where every dealer is verified means that branch is never seen until a judge
#: finds it (the same reasoning PHASE-8 §5 gives for deterministic payment failure injection).
_VERIFICATION_WEIGHTS: tuple[tuple[VerificationStatus, float], ...] = (
    (VerificationStatus.VERIFIED, 0.70),
    (VerificationStatus.PENDING, 0.18),
    (VerificationStatus.UNVERIFIED, 0.12),
)


class RealWorldCollisionError(ValueError):
    """A generated dealer name matched a real brand or a known real dealership string."""


#: Real dealer-group names that a plausible-sounding generator could stumble onto. Small and
#: illustrative rather than exhaustive: the brand pool below is the load-bearing half, since
#: `Listing.brand` already contains 24 real manufacturer names and those are the strings most
#: likely to leak into a dealer name by accident.
KNOWN_REAL_DEALER_GROUPS: tuple[str, ...] = (
    "emil frey",
    "penske",
    "autonation",
    "arnold clark",
    "sytner",
    "pendragon",
    "lookers",
    "van mossel",
    "louwman",
    "porsche holding",
)


def real_world_denylist() -> tuple[str, ...]:
    """Every string a generated dealer name must not contain, lowercased.

    Built from the live brand pool rather than a hand-copied list, so adding a brand to
    `taxonomy.BRAND_TIERS` automatically widens the check instead of silently leaving a gap.
    """
    return tuple(sorted({brand.lower() for brand in all_brands()} | set(KNOWN_REAL_DEALER_GROUPS)))


def assert_no_real_world_collisions(dealers: tuple[Dealer, ...]) -> None:
    """Gate 13.3's mechanism. Raises rather than returns a bool -- a directory that collides
    with a real business is not a result to branch on, it is a bug to stop on."""
    denylist = real_world_denylist()
    for dealer in dealers:
        haystack = f"{dealer.legal_name} {dealer.display_name}".lower()
        for term in denylist:
            if term in haystack:
                raise RealWorldCollisionError(
                    f"generated dealer {dealer.display_name!r} contains the real-world "
                    f"term {term!r}"
                )


def _phone(country: str, rng: random.Random) -> str:
    area, exchange, line = rng.randint(20, 89), rng.randint(100, 999), rng.randint(1000, 9999)
    return f"{_DIAL_CODE[country]} {area} {exchange} {line}"


def _rating(rng: random.Random) -> Decimal:
    """Skewed high, the way a live marketplace's visible ratings actually are -- a directory
    of uniformly-distributed 0.0-5.0 scores looks synthetic immediately. One decimal place,
    matching `Dealer.rating`'s own constraint."""
    value = min(max(rng.gauss(4.3, 0.45), 2.6), 5.0)
    return Decimal(str(round(value, 1)))


def generate_dealers(seed: int, sources: tuple[str, ...]) -> tuple[Dealer, ...]:
    """The whole directory. Same seed and sources in, byte-identical directory out.

    Ordered by `(source, city, index)` -- deterministic iteration, never a `set`, for the
    same reason `generate_catalogue` avoids one (gate 13.2 compares two runs byte for byte).
    """
    rng = random.Random(seed)
    dealers: list[Dealer] = []

    for source in sources:
        counter = 0
        for city in CITIES:
            for _ in range(DEALERS_PER_CITY):
                counter += 1
                dealer_ref = f"{source.split('_')[-1][:2].upper()}-D{counter:03d}"
                prefix = rng.choice(_PREFIXES)
                core = rng.choice(_CORES)
                display_name = f"{prefix} {core} {city.name}"
                legal_name = f"{prefix} {core} {_LEGAL_FORM[city.country]}"
                status = rng.choices(
                    [s for s, _ in _VERIFICATION_WEIGHTS],
                    weights=[w for _, w in _VERIFICATION_WEIGHTS],
                )[0]
                dealers.append(
                    Dealer(
                        id=dealer_uuid(source, dealer_ref),
                        source=source,
                        dealer_ref=dealer_ref,
                        legal_name=legal_name,
                        display_name=display_name,
                        address=(
                            f"{rng.choice(_STREETS_BY_COUNTRY[city.country])} {rng.randint(2, 240)}"
                        ),
                        city=city.name,
                        country=city.country,
                        phone=_phone(city.country, rng),
                        rating=_rating(rng),
                        review_count=rng.randint(12, 940),
                        verification_status=status,
                        marketplace_profile_url=(
                            f"https://{source.replace('_', '-')}.example/dealers/"
                            f"{dealer_ref.lower()}"
                        ),
                    )
                )

    directory = tuple(dealers)
    # Checked at generation time, not only in the gate: a colliding name must never reach a
    # catalogue in the first place, and the gate asserting it is the second line of defence.
    assert_no_real_world_collisions(directory)
    return directory


def dealers_by_source_and_city(
    dealers: tuple[Dealer, ...],
) -> dict[tuple[str, str], tuple[Dealer, ...]]:
    """Index for `generate_catalogue`'s assignment step. Insertion-ordered, so iterating it
    is as deterministic as the directory it was built from."""
    index: dict[tuple[str, str], list[Dealer]] = {}
    for dealer in dealers:
        index.setdefault((dealer.source, dealer.city), []).append(dealer)
    return {key: tuple(value) for key, value in index.items()}
