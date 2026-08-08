"""Pure domain. No I/O, no network, no clock, no framework (CONSTITUTION II.1).

That constraint is what makes P5's scorer testable with no fixtures, no mocks and no event
loop. It is enforced twice -- by a ruff ban and by `tests/test_layer_boundary.py` -- because
the lint rule catches it while you type and the test catches it when someone adds a `# noqa`.
"""

from src.domain.booking import Booking, BookingDraft, BookingState, Customer
from src.domain.dates import DateRange
from src.domain.enums import (
    BrandTier,
    Currency,
    EfficiencyUnit,
    FuelType,
    MarketplaceKind,
    OfferType,
    PowertrainArchetype,
    TimingMechanism,
    Transmission,
    VehicleCategory,
)
from src.domain.listing import (
    SCHEMA_VERSION,
    Efficiency,
    Listing,
    ListingSummary,
    Location,
    RentalRates,
    listing_uuid,
)
from src.domain.marketplace import (
    MAX_PAGE_SIZE,
    MAX_SUMMARY_TOKENS,
    AdapterInfo,
    Availability,
    AvailabilityStatus,
    GeoPoint,
    Quote,
    QuoteLine,
    QuoteTerms,
    SearchPage,
    SearchQuery,
    SortKey,
    estimate_tokens,
    summary_token_estimate,
)
from src.domain.memory import DecisionEntry, DecisionKind, MemoryKind, MemoryRecord
from src.domain.money import CurrencyMismatchError, Money
from src.domain.profile import HardFilter, RequirementProfile, Slot
from src.domain.scoring import (
    CriterionScore,
    CriterionWeight,
    FieldRef,
    RankedResult,
    ScoreBreakdown,
    WeightSet,
)
from src.domain.tco import TcoComparison, TcoEstimate, TcoLine, TcoLineKind, TcoPath

__all__ = [
    "MAX_PAGE_SIZE",
    "MAX_SUMMARY_TOKENS",
    "SCHEMA_VERSION",
    "AdapterInfo",
    "Availability",
    "AvailabilityStatus",
    "Booking",
    "BookingDraft",
    "BookingState",
    "BrandTier",
    "CriterionScore",
    "CriterionWeight",
    "Currency",
    "CurrencyMismatchError",
    "Customer",
    "DateRange",
    "DecisionEntry",
    "DecisionKind",
    "Efficiency",
    "EfficiencyUnit",
    "FieldRef",
    "FuelType",
    "GeoPoint",
    "HardFilter",
    "Listing",
    "ListingSummary",
    "Location",
    "MarketplaceKind",
    "MemoryKind",
    "MemoryRecord",
    "Money",
    "OfferType",
    "PowertrainArchetype",
    "Quote",
    "QuoteLine",
    "QuoteTerms",
    "RankedResult",
    "RentalRates",
    "RequirementProfile",
    "ScoreBreakdown",
    "SearchPage",
    "SearchQuery",
    "Slot",
    "SortKey",
    "TcoComparison",
    "TcoEstimate",
    "TcoLine",
    "TcoLineKind",
    "TcoPath",
    "TimingMechanism",
    "Transmission",
    "VehicleCategory",
    "WeightSet",
    "estimate_tokens",
    "listing_uuid",
    "summary_token_estimate",
]
