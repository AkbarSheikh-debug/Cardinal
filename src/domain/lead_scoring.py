"""How a lead gets its tier (PLAN-02 P15, §0.5).

Held to exactly the bar `src/domain/scoring.py` is held to (gate 5.9): pure functions of
primitives, stdlib and pydantic only, no clock, no store, no model. Same signals in, same
tier out, twice (gate 15.2) -- because a dealer who gets a different answer on a refresh
stops believing the first one.

**The model never picks the tier.** It may write prose around it; this module computes it,
and every signal that moved it is returned alongside so the "why this tier" panel is the
arithmetic rather than a summary of it.

---

## Income is not an input here, and PLAN-02 §P15 lists it as one

The plan asks for two things that cannot both be true if it is (D-079):

- §0.5 / gate 15.3: every tier traces to named signals whose contributions **sum to the
  score**. Nothing hidden, or the panel is a selection rather than an explanation.
- §P15's privacy rule / gate 15.7: the income band is "an input to the score, **not an output
  on the screen**" -- never shown to a seller, in any tier.

Any scheme that keeps both is invertible. Show every signal and the band's contribution is on
screen. Hide one row and the seller subtracts it from the total. Blend income into a broader
"affordability" signal and a dealer who reads this file -- it is open source -- subtracts the
budget-fit term they can compute from the budget the console already shows them.

So income leaves the score. Three reasons, in the order they actually decided it:

1. The tier answers *how soon*, not *how much*. Urgency is target date, cart-add, checkout --
   all of which are here. Income measures capacity, and folding capacity into urgency makes
   the tier partly a wealth score, which is the version of this feature that gets thrown out
   of a compliance review.
2. It is the strongest reading of §0.3's own rule ("minimum viable granularity at every
   boundary"): the seller-facing boundary now carries no income-derived quantity at all,
   rather than one that is merely hard to invert.
3. It makes gate 15.9 checkable directly and more strongly than the plan asked: not "no
   hidden penalty for `undisclosed`" but *income cannot change a lead's score or tier at all*
   -- assert it across every band and against `None`, and there is nothing left to reason
   about.

`budget_fit` stays, and it is a different thing: what the buyer *told the interview* they
wanted to spend, against this car's price. Stated, not inferred, and already visible to the
seller as part of the requirement summary.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.domain.lead import IntentTier, LeadEvent, LeadScore, LeadSignal

# -- weights ---------------------------------------------------------------------------------

#: Seven signals, weights summing to exactly 1.0 so `score` is always in [0, 1] and a tier
#: threshold means the same thing forever. Ordered by weight, which is also roughly the order
#: PLAN-02 §P15's own table puts them in.
#:
#: The sum is asserted at import rather than in a test: a weight edited to 0.3 without another
#: coming down would silently push every lead up a tier, and the failure would show up as
#: "the dealer says the tiers feel wrong lately" rather than as a red test.
WEIGHTS: dict[str, float] = {
    # Stated, not inferred, and the only signal that speaks directly to *when*.
    "target_date_proximity": 0.28,
    # The strongest behavioural signal short of confirming (PLAN-02 §P15).
    "opened_checkout": 0.22,
    "added_to_cart": 0.16,
    "booking_submitted": 0.14,
    "budget_fit": 0.10,
    "return_sessions": 0.06,
    "corporate_customer": 0.04,
}

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "lead weights must sum to 1.0"

#: A score at or above each of these is that tier. Chosen so the shapes that matter land
#: where PLAN-02 §P15's table says: cart-add alone with no date is LOW, cart-add with a date
#: a month out is MEDIUM, and cart-add + checkout with a date days away is HIGH.
HIGH_THRESHOLD = 0.60
MEDIUM_THRESHOLD = 0.32

#: A target date this close is maximum urgency; this far out is none. Between them it is
#: linear -- a curve would imply a precision about buyer behaviour nobody here has measured.
URGENT_DAYS = 3
COLD_DAYS = 180

#: What an unstated target date scores. Deliberately low-but-not-zero: no date is weak
#: evidence of no urgency, not proof of it, and zeroing it would let a missing interview slot
#: masquerade as a fact about the buyer.
UNKNOWN_DATE_VALUE = 0.30

#: What an unstated budget scores. Neutral, for the same reason `undisclosed` income is
#: neutral in PLAN-02 §0.3: a buyer who did not say should be neither rewarded nor punished.
UNKNOWN_BUDGET_VALUE = 0.50


# -- normalisation (pure functions of primitives) ---------------------------------------------


def normalise_target_date(target: date | None, *, today: date) -> tuple[float, str]:
    """Days until the buyer said they need the car. `today` is passed in -- this module reads
    no clock (CONSTITUTION II.1), which is also what makes gate 15.2's determinism testable
    rather than a property that happens to hold within one second."""
    if target is None:
        return UNKNOWN_DATE_VALUE, "no target date given"
    days = (target - today).days
    if days <= URGENT_DAYS:
        # Includes dates already past: a buyer whose deadline has arrived is not less urgent.
        return 1.0, f"target date is {days} day(s) away" if days >= 0 else "target date has passed"
    if days >= COLD_DAYS:
        return 0.0, f"target date is {days} days away"
    value = (COLD_DAYS - days) / (COLD_DAYS - URGENT_DAYS)
    return value, f"target date is {days} days away"


def normalise_budget_fit(budget: Decimal | None, price: Decimal | None) -> tuple[float, str]:
    """How comfortably this car fits what the buyer said they wanted to spend.

    Over budget decays rather than dropping to zero: a car 5% over what someone said is a
    conversation a dealer should still have, and a cliff there would hide exactly the leads
    worth a phone call.
    """
    if budget is None or budget <= 0:
        return UNKNOWN_BUDGET_VALUE, "no budget stated yet"
    if price is None:
        return UNKNOWN_BUDGET_VALUE, "this car has no listed price"
    ratio = float(price / budget)
    if ratio <= 1.0:
        return 1.0, f"priced at {ratio:.0%} of their stated budget"
    # 1.0x -> 1.0, 1.5x or worse -> 0.0.
    value = max(0.0, 1.0 - (ratio - 1.0) / 0.5)
    return value, f"priced at {ratio:.0%} of their stated budget"


def normalise_return_sessions(sessions: int) -> tuple[float, str]:
    """Coming back is evidence; coming back a lot is not proportionally more evidence, so this
    saturates at three rather than climbing forever."""
    count = max(1, sessions)
    if count <= 1:
        return 0.0, "first session"
    if count == 2:
        return 0.5, "returned once"
    return 1.0, f"returned {count - 1} times"


def _event_signal(present: bool, name: str, yes: str, no: str) -> LeadSignal:
    value = 1.0 if present else 0.0
    weight = WEIGHTS[name]
    return LeadSignal(
        name=name,
        value=value,
        weight=weight,
        contribution=weight * value,
        explanation=yes if present else no,
    )


def tier_for(score: float) -> IntentTier:
    if score >= HIGH_THRESHOLD:
        return IntentTier.HIGH
    if score >= MEDIUM_THRESHOLD:
        return IntentTier.MEDIUM
    return IntentTier.LOW


def explain(tier: IntentTier, signals: tuple[LeadSignal, ...]) -> str:
    """One sentence, generated here rather than by a model.

    PLAN-02 §0.5 allows the model to write it; this doesn't, and the reason is `DEMO_MODE`:
    a sentence that needs an API key is a sentence that is missing on the machine a judge
    runs (CONSTITUTION III.7). Every word of it is derived from the signals it names.
    """
    top = [s for s in sorted(signals, key=lambda s: -s.contribution) if s.contribution > 0][:3]
    reasons = ", ".join(s.explanation for s in top) if top else "no strong signals yet"
    return f"{tier.label} — {reasons}."


def score_lead(
    *,
    events: tuple[LeadEvent, ...],
    target_date: date | None,
    today: date,
    budget: Decimal | None,
    price: Decimal | None,
    return_sessions: int = 1,
    is_corporate: bool = False,
) -> LeadScore:
    """The whole scorer. Seven named signals in, one `LeadScore` out.

    Note what this signature does *not* accept: there is no income parameter, no account, and
    no store to reach one through. The privacy property is structural rather than a rule
    somebody has to keep following (this module's docstring, D-079).
    """
    date_value, date_why = normalise_target_date(target_date, today=today)
    budget_value, budget_why = normalise_budget_fit(budget, price)
    sessions_value, sessions_why = normalise_return_sessions(return_sessions)

    signals: tuple[LeadSignal, ...] = (
        LeadSignal(
            name="target_date_proximity",
            value=date_value,
            weight=WEIGHTS["target_date_proximity"],
            contribution=WEIGHTS["target_date_proximity"] * date_value,
            explanation=date_why,
        ),
        _event_signal(
            LeadEvent.CHECKOUT_OPENED in events,
            "opened_checkout",
            "opened checkout",
            "has not opened checkout",
        ),
        _event_signal(
            LeadEvent.CART_ADD in events,
            "added_to_cart",
            "added this car to their cart",
            "not in their cart",
        ),
        _event_signal(
            LeadEvent.BOOKING_SUBMITTED in events,
            "booking_submitted",
            "submitted a booking form",
            "no booking form submitted",
        ),
        LeadSignal(
            name="budget_fit",
            value=budget_value,
            weight=WEIGHTS["budget_fit"],
            contribution=WEIGHTS["budget_fit"] * budget_value,
            explanation=budget_why,
        ),
        LeadSignal(
            name="return_sessions",
            value=sessions_value,
            weight=WEIGHTS["return_sessions"],
            contribution=WEIGHTS["return_sessions"] * sessions_value,
            explanation=sessions_why,
        ),
        _event_signal(
            is_corporate,
            "corporate_customer",
            "buying as a business",
            "buying as an individual",
        ),
    )

    total = sum(s.contribution for s in signals)
    tier = tier_for(total)
    return LeadScore(tier=tier, score=total, signals=signals, explanation=explain(tier, signals))
