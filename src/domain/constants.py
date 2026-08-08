"""TCO and running-cost constants (PHASE-5 SS10 risk: "TCO looks authoritative but rests on
invented constants"). Mitigated the way the risk table prescribes -- every number lives in
this one file with a comment on where the estimate comes from, instead of being scattered as
magic literals through `costs.py` and `tco.py`.

These are flat, illustrative estimates sized for a synthetic catalogue, not a regional
pricing table -- regional tax/insurance/energy tables are PHASE-5 SS2's explicit `[SCALE]`
line. Any UI that renders a TCO figure built from these must flag it as illustrative
(PHASE-5 SS10).
"""

from __future__ import annotations

from decimal import Decimal

# -- one-time, buy path only --------------------------------------------------------------

REGISTRATION_FEE = Decimal("250")
TRANSFER_FEE = Decimal("120")

# -- annual road tax -------------------------------------------------------------------------
# Real jurisdictions band this by emissions or displacement and usually discount or waive it
# for EVs; simplified here to two flat figures rather than modelling a table ([SCALE]).

ROAD_TAX_ANNUAL = Decimal("140")
ROAD_TAX_ANNUAL_ELECTRIC = Decimal("40")

# -- insurance -------------------------------------------------------------------------------
# `Listing.insurance_band` runs 1..20 (PHASE-1 SS4). A real premium is not linear in band,
# but linear is the honest amount of modelling for an MVP over a synthetic band number.

INSURANCE_BASE_MONTHLY = Decimal("35")
INSURANCE_PER_BAND_MONTHLY = Decimal("7")

# -- energy ----------------------------------------------------------------------------------
# EUR/litre (petrol and diesel blended) and EUR/kWh (home-charging blended), both flat
# mid-2020s EU retail estimates -- not the per-country table PHASE-5 SS2 defers to [SCALE].

FUEL_PRICE_PER_LITRE = Decimal("1.75")
ELECTRICITY_PRICE_PER_KWH = Decimal("0.32")

# -- maintenance -----------------------------------------------------------------------------
# Baseline wear-and-tear (tyres, fluids, brakes). A belt service (~EUR900 roughly every
# 100,000 km -- see `TimingMechanism`) amortises to a monthly surcharge; a BEV has no oil
# service to schedule at all, which nets out as a discount rather than a separate branch.

MAINTENANCE_BASE_MONTHLY = Decimal("25")
TIMING_BELT_MONTHLY_SURCHARGE = Decimal("15")
BEV_MAINTENANCE_DISCOUNT_MONTHLY = Decimal("10")

# -- usage -------------------------------------------------------------------------------------
# ~15,000 km/year, a common EU average-driver assumption. Used to turn a per-100km efficiency
# figure into a monthly energy cost and to size a rental's excess-mileage exposure.

AVG_KM_PER_MONTH = 1250
