"""Deterministic catalogue generation. Pure -- no clock, no network, no database."""

from src.adapters.catalogue.generator import (
    CATALOGUE_EPOCH,
    DEFAULT_SEED,
    DEFAULT_TOTAL,
    MIN_BRANDS_PER_CATEGORY,
    PRICE_NOISE_SIGMA,
    SOURCE_DEALER,
    SOURCE_RENTAL,
    expected_market_value_eur,
    generate_catalogue,
)

__all__ = [
    "CATALOGUE_EPOCH",
    "DEFAULT_SEED",
    "DEFAULT_TOTAL",
    "MIN_BRANDS_PER_CATEGORY",
    "PRICE_NOISE_SIGMA",
    "SOURCE_DEALER",
    "SOURCE_RENTAL",
    "expected_market_value_eur",
    "generate_catalogue",
]
