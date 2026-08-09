"""`Listing` <-> `ListingRow`.

`to_listing` reads only the `canonical` document. The projected columns exist so Postgres
can filter and sort; they are never the thing a `Listing` is rebuilt from, which keeps the
round-trip exact and keeps a mis-projected column from silently corrupting a record.
"""

from __future__ import annotations

from src.adapters.db.models import DealerRow, ListingRow
from src.domain.dealer import Dealer
from src.domain.listing import Listing


def dealer_to_row(dealer: Dealer) -> DealerRow:
    return DealerRow(
        id=dealer.id,
        source=dealer.source,
        dealer_ref=dealer.dealer_ref,
        legal_name=dealer.legal_name,
        display_name=dealer.display_name,
        city=dealer.city,
        country=dealer.country,
        verification_status=dealer.verification_status.value,
        canonical=dealer.model_dump(mode="json"),
    )


def to_dealer(row: DealerRow) -> Dealer:
    """`canonical` only, same discipline as `to_listing` -- a mis-projected column can never
    corrupt the record it was projected from."""
    return Dealer.model_validate(row.canonical)


def to_row(listing: Listing) -> ListingRow:
    rates = listing.rental_rates
    return ListingRow(
        id=listing.id,
        schema_version=listing.schema_version,
        source=listing.source,
        source_id=listing.source_id,
        fetched_at=listing.fetched_at,
        withdrawn_at=listing.withdrawn_at,
        dealer_id=listing.dealer_id,
        brand=listing.brand,
        model=listing.model,
        variant=listing.variant,
        year=listing.year,
        category=listing.category.value,
        condition=listing.condition.value,
        offer_type=listing.offer_type.value,
        market_value_amount=listing.market_value.amount,
        market_value_currency=listing.market_value.currency.value,
        price_buy_amount=listing.price_buy.amount if listing.price_buy else None,
        rental_daily_amount=rates.daily.amount if rates else None,
        mileage_km=listing.mileage_km,
        fuel_type=listing.fuel_type.value,
        transmission=listing.transmission.value,
        seats=listing.seats,
        doors=listing.doors,
        insurance_band=listing.insurance_band,
        service_interval_km=listing.service_interval_km,
        timing_mechanism=listing.timing_mechanism.value,
        powertrain_archetype=listing.powertrain_archetype.value,
        city=listing.location.city,
        country=listing.location.country,
        latitude=listing.location.latitude,
        longitude=listing.location.longitude,
        available_from=listing.available_from,
        description=listing.description,
        raw=listing.raw,
        canonical=listing.model_dump(mode="json"),
    )


def to_listing(row: ListingRow) -> Listing:
    return Listing.model_validate(row.canonical)
