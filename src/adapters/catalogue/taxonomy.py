"""The vocabulary the generator draws from.

Hand-written on purpose. PHASE-1 §8 lists "mock data looks obviously fake in the demo" as
the top risk, and the cheapest defence is that every (brand, model) pair in here is a car
that actually exists in that body style. A generator that pairs a random brand with a random
model name produces "Porsche Fabia", and one row like that ends a demo's credibility.

Brand names in our own generated dataset are fine; outbound calls to a BMW Group endpoint
are not (CONSTITUTION I.3). Nothing in this module makes a network call.
"""

from __future__ import annotations

from typing import NamedTuple

from src.domain.enums import BrandTier, FuelType, PowertrainArchetype, VehicleCategory

# ---------------------------------------------------------------------------
# Brands
# ---------------------------------------------------------------------------

#: The 24-brand pool from PHASE-1 §4.
BRAND_TIERS: dict[str, BrandTier] = {
    "Tata": BrandTier.BUDGET,
    "Mahindra": BrandTier.BUDGET,
    "MG": BrandTier.BUDGET,
    "Suzuki": BrandTier.BUDGET,
    "Toyota": BrandTier.MAINSTREAM,
    "Honda": BrandTier.MAINSTREAM,
    "Hyundai": BrandTier.MAINSTREAM,
    "Kia": BrandTier.MAINSTREAM,
    "Ford": BrandTier.MAINSTREAM,
    "VW": BrandTier.MAINSTREAM,
    "Škoda": BrandTier.MAINSTREAM,
    "Renault": BrandTier.MAINSTREAM,
    "Peugeot": BrandTier.MAINSTREAM,
    "Nissan": BrandTier.MAINSTREAM,
    "Mazda": BrandTier.MAINSTREAM,
    "BYD": BrandTier.MAINSTREAM,
    "Volvo": BrandTier.PREMIUM,
    "Audi": BrandTier.PREMIUM,
    "BMW": BrandTier.PREMIUM,
    "Tesla": BrandTier.PREMIUM,
    "Polestar": BrandTier.PREMIUM,
    "Mercedes-Benz": BrandTier.LUXURY,
    "Jaguar": BrandTier.LUXURY,
    "Porsche": BrandTier.LUXURY,
}

#: Brands that only ever build battery-electric cars.
ALWAYS_ELECTRIC_BRANDS = frozenset({"Tesla", "Polestar"})


class ModelSpec(NamedTuple):
    """One real (brand, model) pair, plus any fact that overrides the category default.

    `archetype` exists because category and brand tier together still can't tell you how
    many cylinders a specific car has. Left to the category default, a Mazda MX-5 comes out
    with a V6 and a Mahindra van with a V6 -- both four-cylinder cars in reality, and both
    the kind of row that costs the catalogue its credibility with anyone who knows cars.
    Annotated where the real answer is known and the default would be wrong; left `None`
    everywhere the category default is already plausible.
    """

    brand: str
    model: str
    fuel: FuelType | None = None
    seats: int | None = None
    archetype: PowertrainArchetype | None = None


# Local aliases -- the annotated tables below are long enough without the full enum paths.
_I3T = PowertrainArchetype.I3_TURBO
_I4NA = PowertrainArchetype.I4_NA
_I4T = PowertrainArchetype.I4_TURBO
_V6 = PowertrainArchetype.V6
_V8 = PowertrainArchetype.V8
_PETROL = FuelType.PETROL
_DIESEL = FuelType.DIESEL

# Note on the six-cylinder cars: the archetype set has no inline-six, so a BMW M4 and a
# Porsche 911 are both filed under `V6`. That is the nearest of the eight available
# cutaways, and P6 renders "six cylinders" rather than a specific block angle.

# ---------------------------------------------------------------------------
# Models by category -- at least twelve brands each, so the generator can guarantee the
# ten-per-category floor in gate 1.3 with room to spare.
# ---------------------------------------------------------------------------

MODELS_BY_CATEGORY: dict[VehicleCategory, tuple[ModelSpec, ...]] = {
    VehicleCategory.HATCHBACK: (
        ModelSpec("Toyota", "Yaris"),
        ModelSpec("Honda", "Jazz"),
        ModelSpec("Hyundai", "i20"),
        ModelSpec("Kia", "Rio"),
        ModelSpec("Ford", "Fiesta"),
        ModelSpec("VW", "Polo"),
        ModelSpec("Škoda", "Fabia"),
        ModelSpec("Renault", "Clio"),
        ModelSpec("Peugeot", "208"),
        ModelSpec("Nissan", "Micra"),
        ModelSpec("Mazda", "2"),
        ModelSpec("Suzuki", "Swift"),
        ModelSpec("MG", "3"),
        ModelSpec("Tata", "Altroz"),
    ),
    VehicleCategory.SEDAN: (
        ModelSpec("Toyota", "Corolla"),
        ModelSpec("Honda", "Civic"),
        ModelSpec("Hyundai", "Elantra"),
        ModelSpec("Kia", "K5"),
        ModelSpec("Ford", "Mondeo"),
        ModelSpec("VW", "Passat"),
        ModelSpec("Škoda", "Octavia"),
        ModelSpec("Renault", "Talisman"),
        ModelSpec("Peugeot", "508"),
        ModelSpec("Nissan", "Sentra"),
        ModelSpec("Mazda", "6"),
        ModelSpec("Volvo", "S60"),
        ModelSpec("Audi", "A4"),
        ModelSpec("BMW", "3 Series"),
        ModelSpec("Mercedes-Benz", "C-Class"),
        ModelSpec("Tata", "Tigor"),
    ),
    VehicleCategory.SUV: (
        ModelSpec("Toyota", "RAV4"),
        ModelSpec("Honda", "CR-V"),
        ModelSpec("Hyundai", "Tucson"),
        ModelSpec("Kia", "Sportage"),
        ModelSpec("Ford", "Explorer", seats=7),
        ModelSpec("VW", "Tiguan"),
        ModelSpec("Škoda", "Kodiaq", seats=7),
        ModelSpec("Nissan", "X-Trail"),
        ModelSpec("Mazda", "CX-5"),
        ModelSpec("Volvo", "XC60"),
        ModelSpec("Audi", "Q5"),
        ModelSpec("BMW", "X3"),
        ModelSpec("Mercedes-Benz", "GLC"),
        ModelSpec("Mahindra", "XUV700", seats=7),
        ModelSpec("Tata", "Safari", seats=7),
        ModelSpec("MG", "Hector"),
    ),
    VehicleCategory.CROSSOVER: (
        ModelSpec("Toyota", "C-HR"),
        ModelSpec("Honda", "HR-V"),
        ModelSpec("Hyundai", "Kona"),
        ModelSpec("Kia", "Niro", fuel=FuelType.HYBRID),
        ModelSpec("Ford", "Puma"),
        ModelSpec("VW", "T-Roc"),
        ModelSpec("Škoda", "Kamiq"),
        ModelSpec("Renault", "Captur"),
        ModelSpec("Peugeot", "2008"),
        ModelSpec("Nissan", "Juke"),
        ModelSpec("Mazda", "CX-30"),
        ModelSpec("Suzuki", "Vitara"),
        ModelSpec("MG", "ZS"),
        ModelSpec("Tata", "Nexon"),
        ModelSpec("Volvo", "XC40"),
    ),
    VehicleCategory.COUPE: (
        ModelSpec("Toyota", "GR86", _PETROL, 4, _I4NA),
        ModelSpec("Honda", "Prelude", _PETROL, 4, _I4NA),
        ModelSpec("Hyundai", "Veloster", _PETROL, 4, _I4T),
        ModelSpec("Kia", "Stinger", _PETROL, 4, _V6),
        ModelSpec("Ford", "Mustang", _PETROL, 4, _V8),
        ModelSpec("VW", "Scirocco", _PETROL, 4, _I4T),
        ModelSpec("Renault", "Mégane Coupé", _PETROL, 4, _I4T),
        ModelSpec("Peugeot", "RCZ", _PETROL, 4, _I4T),
        ModelSpec("Nissan", "400Z", _PETROL, 2, _V6),
        ModelSpec("Mazda", "RX-8", _PETROL, 4, _I4NA),
        ModelSpec("Audi", "A5", None, 4, _I4T),
        ModelSpec("BMW", "4 Series", None, 4, _I4T),
        ModelSpec("Mercedes-Benz", "CLE", None, 4, _I4T),
        ModelSpec("Jaguar", "F-Type", _PETROL, 2, _V8),
        ModelSpec("Porsche", "718 Cayman", _PETROL, 2, _I4T),
        ModelSpec("Volvo", "C70", None, 4, _I4T),
    ),
    VehicleCategory.CONVERTIBLE: (
        ModelSpec("Mazda", "MX-5", _PETROL, 2, _I4NA),
        ModelSpec("BMW", "Z4", _PETROL, 2, _I4T),
        ModelSpec("Audi", "A5 Cabriolet", None, 4, _I4T),
        ModelSpec("Mercedes-Benz", "SL", _PETROL, 2, _V8),
        ModelSpec("Porsche", "718 Boxster", _PETROL, 2, _I4T),
        ModelSpec("Jaguar", "F-Type Convertible", _PETROL, 2, _V8),
        ModelSpec("VW", "T-Roc Cabriolet", _PETROL, 4, _I4T),
        ModelSpec("Ford", "Mustang Convertible", _PETROL, 4, _V8),
        ModelSpec("Renault", "Mégane CC", None, 4, _I4T),
        ModelSpec("Peugeot", "308 CC", None, 4, _I4T),
        ModelSpec("Volvo", "C70 Cabrio", None, 4, _I4T),
        ModelSpec("Nissan", "370Z Roadster", _PETROL, 2, _V6),
        ModelSpec("Honda", "S2000", _PETROL, 2, _I4NA),
        ModelSpec("Toyota", "GR86 Roadster", _PETROL, 4, _I4NA),
    ),
    VehicleCategory.PICKUP: (
        ModelSpec("Toyota", "Hilux", _DIESEL, None, _I4T),
        ModelSpec("Ford", "Ranger", _DIESEL, None, _I4T),
        ModelSpec("Nissan", "Navara", _DIESEL, None, _I4T),
        ModelSpec("VW", "Amarok", _DIESEL, None, _V6),
        ModelSpec("Mahindra", "Scorpio Pik-Up", _DIESEL, None, _I4T),
        ModelSpec("Tata", "Yodha", _DIESEL, None, _I4T),
        ModelSpec("Mercedes-Benz", "X-Class", _DIESEL, None, _V6),
        ModelSpec("Renault", "Alaskan", _DIESEL, None, _I4T),
        ModelSpec("Peugeot", "Landtrek", _DIESEL, None, _I4T),
        ModelSpec("Mazda", "BT-50", _DIESEL, None, _I4T),
        ModelSpec("Kia", "Tasman", _DIESEL, None, _I4T),
        ModelSpec("Hyundai", "Santa Cruz", _PETROL, None, _I4T),
        ModelSpec("MG", "Extender", _DIESEL, None, _I4T),
        ModelSpec("Suzuki", "Equator", _DIESEL, None, _I4T),
    ),
    VehicleCategory.VAN_MPV: (
        ModelSpec("Toyota", "Proace Verso", _DIESEL, 8, _I4T),
        ModelSpec("Honda", "Odyssey", _PETROL, 7, _V6),
        ModelSpec("Hyundai", "Staria", _DIESEL, 8, _I4T),
        ModelSpec("Kia", "Carnival", _PETROL, 7, _V6),
        ModelSpec("Ford", "Tourneo", _DIESEL, 8, _I4T),
        ModelSpec("VW", "Multivan", None, 7, _I4T),
        ModelSpec("Renault", "Trafic", _DIESEL, 8, _I4T),
        ModelSpec("Peugeot", "Traveller", _DIESEL, 8, _I4T),
        ModelSpec("Nissan", "Primastar", _DIESEL, 8, _I4T),
        ModelSpec("Mercedes-Benz", "V-Class", _DIESEL, 7, _I4T),
        ModelSpec("Suzuki", "Ertiga", _PETROL, 7, _I4NA),
        ModelSpec("Tata", "Winger", _DIESEL, 9, _I4T),
        ModelSpec("MG", "Maxus 9", None, 7, _I4T),
        ModelSpec("Mahindra", "Marazzo", _DIESEL, 7, _I4T),
    ),
    VehicleCategory.WAGON: (
        ModelSpec("VW", "Passat Variant"),
        ModelSpec("Škoda", "Superb Combi"),
        ModelSpec("Audi", "A4 Avant"),
        ModelSpec("BMW", "3 Series Touring"),
        ModelSpec("Mercedes-Benz", "C-Class Estate"),
        ModelSpec("Volvo", "V60"),
        ModelSpec("Peugeot", "308 SW"),
        ModelSpec("Renault", "Mégane Estate"),
        ModelSpec("Toyota", "Corolla Touring Sports"),
        ModelSpec("Kia", "Ceed SW"),
        ModelSpec("Hyundai", "i30 Wagon"),
        ModelSpec("Ford", "Focus Estate"),
        ModelSpec("Mazda", "6 Wagon"),
        ModelSpec("Jaguar", "XF Sportbrake"),
    ),
    VehicleCategory.ELECTRIC: (
        ModelSpec("Tesla", "Model 3"),
        ModelSpec("BYD", "Atto 3"),
        ModelSpec("Polestar", "2"),
        ModelSpec("VW", "ID.4"),
        ModelSpec("Hyundai", "Ioniq 5"),
        ModelSpec("Kia", "EV6"),
        ModelSpec("Nissan", "Leaf"),
        ModelSpec("Renault", "Mégane E-Tech"),
        ModelSpec("Peugeot", "e-208"),
        ModelSpec("Volvo", "EX30"),
        ModelSpec("Audi", "Q4 e-tron"),
        ModelSpec("BMW", "i4"),
        ModelSpec("Mercedes-Benz", "EQB"),
        ModelSpec("MG", "4"),
        ModelSpec("Tata", "Nexon EV"),
        ModelSpec("Toyota", "bZ4X"),
        ModelSpec("Ford", "Mustang Mach-E"),
    ),
    VehicleCategory.LUXURY: (
        ModelSpec("Mercedes-Benz", "S-Class"),
        ModelSpec("BMW", "7 Series"),
        ModelSpec("Audi", "A8"),
        ModelSpec("Jaguar", "XJ", _PETROL, None, _V8),
        ModelSpec("Porsche", "Panamera", seats=4),
        ModelSpec("Volvo", "S90"),
        ModelSpec("Tesla", "Model S"),
        ModelSpec("Polestar", "3"),
        ModelSpec("VW", "Arteon"),
        ModelSpec("Toyota", "Crown"),
        ModelSpec("Hyundai", "Grandeur"),
        ModelSpec("Kia", "K8"),
        ModelSpec("Nissan", "Maxima Platinum"),
        ModelSpec("Mazda", "CX-90 Signature", seats=7),
    ),
    VehicleCategory.SPORTS: (
        ModelSpec("Porsche", "911", _PETROL, 4, _V6),
        ModelSpec("BMW", "M4", _PETROL, 4, _V6),
        ModelSpec("Audi", "RS5", _PETROL, 4, _V6),
        ModelSpec("Mercedes-Benz", "AMG GT", _PETROL, 2, _V8),
        ModelSpec("Jaguar", "F-Type R", _PETROL, 2, _V8),
        ModelSpec("Toyota", "GR Supra", _PETROL, 2, _V6),
        ModelSpec("Honda", "Civic Type R", _PETROL, None, _I4T),
        ModelSpec("Nissan", "GT-R", _PETROL, 4, _V6),
        ModelSpec("Ford", "Mustang GT", _PETROL, 4, _V8),
        ModelSpec("Mazda", "MX-5 RF", _PETROL, 2, _I4NA),
        ModelSpec("VW", "Golf R", _PETROL, None, _I4T),
        ModelSpec("Renault", "Mégane RS", _PETROL, None, _I4T),
        ModelSpec("Hyundai", "i30 N", _PETROL, None, _I4T),
        ModelSpec("Kia", "Stinger GT", _PETROL, 4, _V6),
        ModelSpec("Tesla", "Model 3 Performance"),
        ModelSpec("Polestar", "2 BST"),
    ),
}


# ---------------------------------------------------------------------------
# Category shape
# ---------------------------------------------------------------------------


class CategoryShape(NamedTuple):
    doors: int
    seats: int
    #: Value of a new example of this category at mainstream tier, in EUR.
    base_value_eur: int
    #: Weights over petrol / diesel / hybrid / phev for non-electric categories.
    fuel_mix: tuple[float, float, float, float]


CATEGORY_SHAPES: dict[VehicleCategory, CategoryShape] = {
    VehicleCategory.HATCHBACK: CategoryShape(5, 5, 15_000, (0.62, 0.14, 0.20, 0.04)),
    VehicleCategory.SEDAN: CategoryShape(4, 5, 22_000, (0.45, 0.26, 0.22, 0.07)),
    VehicleCategory.SUV: CategoryShape(5, 5, 30_000, (0.36, 0.34, 0.20, 0.10)),
    VehicleCategory.CROSSOVER: CategoryShape(5, 5, 24_000, (0.48, 0.18, 0.26, 0.08)),
    VehicleCategory.COUPE: CategoryShape(2, 4, 32_000, (0.78, 0.10, 0.08, 0.04)),
    VehicleCategory.CONVERTIBLE: CategoryShape(2, 4, 36_000, (0.82, 0.08, 0.06, 0.04)),
    VehicleCategory.PICKUP: CategoryShape(4, 5, 34_000, (0.24, 0.64, 0.06, 0.06)),
    VehicleCategory.VAN_MPV: CategoryShape(5, 7, 33_000, (0.26, 0.54, 0.14, 0.06)),
    VehicleCategory.WAGON: CategoryShape(5, 5, 26_000, (0.38, 0.36, 0.18, 0.08)),
    VehicleCategory.ELECTRIC: CategoryShape(5, 5, 35_000, (0.0, 0.0, 0.0, 0.0)),
    VehicleCategory.LUXURY: CategoryShape(4, 5, 65_000, (0.34, 0.26, 0.20, 0.20)),
    VehicleCategory.SPORTS: CategoryShape(2, 4, 60_000, (0.80, 0.02, 0.04, 0.14)),
}

#: Multiplier on `base_value_eur`. A budget-brand SUV and a luxury-brand SUV are not the
#: same purchase, and a catalogue that prices them alike makes every ranking look broken.
TIER_VALUE_MULTIPLIER: dict[BrandTier, float] = {
    BrandTier.BUDGET: 0.72,
    BrandTier.MAINSTREAM: 1.00,
    BrandTier.PREMIUM: 1.45,
    BrandTier.LUXURY: 2.10,
}


# ---------------------------------------------------------------------------
# Trim names and locations
# ---------------------------------------------------------------------------

TRIMS_BY_TIER: dict[BrandTier, tuple[str, ...]] = {
    BrandTier.BUDGET: ("XE", "XM", "XZ", "Sigma", "Delta"),
    BrandTier.MAINSTREAM: ("Active", "Style", "Comfortline", "GT-Line", "Titanium", "Elegance"),
    BrandTier.PREMIUM: ("S line", "M Sport", "R-Design", "Ultimate", "Plus", "Momentum"),
    BrandTier.LUXURY: ("AMG Line", "Exclusive", "Turbo S", "R-Dynamic", "First Edition"),
}


class City(NamedTuple):
    name: str
    country: str
    latitude: float
    longitude: float


CITIES: tuple[City, ...] = (
    City("Berlin", "DE", 52.5200, 13.4050),
    City("Munich", "DE", 48.1351, 11.5820),
    City("Hamburg", "DE", 53.5511, 9.9937),
    City("Amsterdam", "NL", 52.3676, 4.9041),
    City("Rotterdam", "NL", 51.9244, 4.4777),
    City("Brussels", "BE", 50.8503, 4.3517),
    City("Paris", "FR", 48.8566, 2.3522),
    City("Lyon", "FR", 45.7640, 4.8357),
    City("Vienna", "AT", 48.2082, 16.3738),
    City("Zurich", "CH", 47.3769, 8.5417),
    City("Prague", "CZ", 50.0755, 14.4378),
    City("Warsaw", "PL", 52.2297, 21.0122),
    City("Milan", "IT", 45.4642, 9.1900),
    City("Madrid", "ES", 40.4168, -3.7038),
    City("Lisbon", "PT", 38.7223, -9.1393),
    City("Dublin", "IE", 53.3498, -6.2603),
    City("Copenhagen", "DK", 55.6761, 12.5683),
    City("Stockholm", "SE", 59.3293, 18.0686),
)


def brand_tier(brand: str) -> BrandTier:
    return BRAND_TIERS[brand]


def all_brands() -> tuple[str, ...]:
    return tuple(BRAND_TIERS)


def brands_in_category(category: VehicleCategory) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for spec in MODELS_BY_CATEGORY[category]:
        seen.setdefault(spec.brand, None)
    return tuple(seen)
