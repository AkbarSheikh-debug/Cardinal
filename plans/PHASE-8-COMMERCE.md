# PHASE 8 — Commerce

**Owns:** the transaction. Booking lifecycle, the mock payment gateway, financing, idempotency, and
the human-click invariant.

The brief says the payment flow must be "completely mocked and safe." The temptation is to mock
*everything* — a button that sets a flag. Resist it. **Mock the gateway; build the lifecycle.**
A mock that skips the hard parts teaches you nothing and gets thrown away; a mock that only replaces
the network call is swapped for Stripe in an afternoon.

---

## 1. Objective

A real booking state machine with a fake payment gateway, idempotent, auditable, and structurally
incapable of being confirmed by the agent.

## 2. Scope

### In
- `[MVP]` Booking lifecycle state machine (§3)
- `[MVP]` Idempotency keys on every mutating operation
- `[MVP]` Mock gateway with **deterministic failure injection** (§5)
- `[MVP]` `ui://checkout/payment` — the checkout App (brief requirement R4)
- `[MVP]` Financing calculator (term / APR / down payment → monthly)
- `[MVP]` The human-click invariant, enforced by tool visibility
- `[MVP]` Immutable audit trail
- `[SCALE]` Gateway abstraction seam + a real provider behind a flag
- `[SCALE]` Refund / cancellation flows, partial states
- `[SCALE]` Webhook receiver pattern for async settlement

### Out
- The host that renders the App — P7. This phase owns what's *inside* it.

---

## 3. Booking lifecycle

```
                  ┌──────────────── expire (TTL) ─────────────┐
                  ▼                                            │
  DRAFT ──submit──▶ PENDING ──authorise──▶ CONFIRMED ──▶ (terminal)
    │                  │                       │
    │                  ├─decline──▶ FAILED     └──cancel──▶ CANCELLED
    └──abandon──▶ ABANDONED
```

Six states, explicit transitions, no others. Rules:

- **Transitions are validated, not assumed.** `PENDING → CONFIRMED` requires a successful
  authorisation record; there's no code path that sets `CONFIRMED` directly.
- **`DRAFT` and `Booking` are different types** (P0 §4). A draft has no row in `bookings`; promoting
  one is an explicit, audited transition — which is what makes "the agent prepared a booking" and
  "a booking exists" different facts.
- **`PENDING` has a TTL.** An abandoned checkout must not hold inventory forever. 15 minutes, then
  `EXPIRED`, then the listing is released.
- Every transition appends to the audit trail: actor (`user` / `agent` / `system`), timestamp,
  from-state, to-state, and the triggering event id.

Exhaustive test: for all `(state, event)` pairs, either a defined transition or an explicit
rejection. No silent no-ops.

---

## 4. The human-click invariant

> Constitution rule II.2. The single most important line in the codebase.

```jsonc
{"name": "confirm_booking",
 "_meta": {"ui": {"visibility": ["app"]}}}     // ← not ["model", "app"]
```

`visibility: ["app"]` means the tool is **absent from the tool list the model receives**. There is no
prompt to jailbreak, no permission callback to race, no reasoning path that arrives at it. The
model can prepare, pre-fill, recommend, and explain; it cannot confirm.

Defence in depth, in order of strength:

1. **Tool visibility** — the wall. The model literally cannot see the tool.
2. **`can_use_tool` callback** — denies it server-side if the visibility config is ever wrong.
3. **Server-side gesture requirement** — `confirm_booking` requires a `gesture_token` minted by the
   App on a real `click` event (with `isTrusted === true`) and valid for 30 seconds.
4. **Audit** — every confirmation records the gesture token and its origin.

Layer 3 matters because it survives a future refactor that accidentally widens visibility. Layers
are cheap; a confirmed booking nobody clicked is not.

---

## 5. The mock gateway

`src/adapters/payments/mock.py` implements a `PaymentGateway` protocol:

```python
class PaymentGateway(Protocol):
    async def authorise(self, intent: PaymentIntent, idem: str) -> AuthResult: ...
    async def capture(self, auth_id: str, idem: str) -> CaptureResult: ...
    async def void(self, auth_id: str, idem: str) -> VoidResult: ...
```

That protocol is the seam. Swapping in a real provider later is one new file implementing three
methods — nothing above it changes.

### Deterministic failure injection

A gateway that always succeeds means the decline path is never built, never rendered, and never
rehearsed — and then a judge clicks something unexpected and the demo shows a spinner forever.

Mock outcomes are **deterministic on the card number**, so every path is reachable and testable:

| Test card | Outcome |
|---|---|
| `4242 4242 4242 4242` | Success |
| `4000 0000 0000 0002` | Declined — insufficient funds |
| `4000 0000 0000 0069` | Declined — expired card |
| `4000 0000 0000 0119` | Gateway error (500) |
| `4000 0000 0000 0127` | Timeout (no response) |

Mirroring Stripe's test-card conventions is deliberate: it's a familiar vocabulary, and it means the
test suite carries over unchanged when a real gateway lands.

### Safety

- **No payment SDK anywhere.** Not in `requirements.txt`, not commented out, not in a lockfile.
- **No card data is stored.** The mock computes an outcome from the number and discards it. Card
  fields never leave the App's iframe except as a last-4 + outcome code.
- **The mock cannot be pointed at a real endpoint.** Its base URL is a compile-time constant, not
  configuration.
- **The banner is not optional.** `MOCK — NO REAL PAYMENT` renders unconditionally, above the fold,
  and is asserted by the gate.

---

## 6. Idempotency

Every mutating call carries a client-generated `idempotency_key`. Server stores
`(key → response)` for 24 hours and replays the stored response on a repeat.

Why it's MVP rather than scale: a double-click on "Confirm", a retried request after a flaky
connection, or the user hitting back and resubmitting are all *ordinary* and all produce two
bookings without this. It is twenty lines and it is the difference between a demo and a system.

`UNIQUE` constraint on `bookings.idempotency_key` as the backstop — application logic can be raced;
the database cannot.

---

## 7. Financing

Inside the checkout App: term (12–72 months), down payment (0–40%), APR. Standard amortisation:

```
principal = price × (1 − down%)
r = apr / 12
monthly = principal × r / (1 − (1+r)^−term)
```

Computed **in the App** for instant feedback, and re-computed **server-side** on submit — the
displayed figure is never trusted. Client-side maths for responsiveness, server-side for truth, is
the general rule and it applies even when the money is fake.

This is what makes the required checkout App *do* something rather than merely collect a card
number, and it's the natural place a real product would surface partner lender offers.

---

## 8. Exit gate

`scripts/gate_phase8.py`:

| # | Criterion |
|---|---|
| 8.1 | State machine: all `(state, event)` pairs either transition or explicitly reject — no silent no-ops |
| 8.2 | `confirm_booking` is absent from the model's resolved toolset (asserted from SDK state) |
| 8.3 | No agent-driven path reaches `confirm_booking` — Playwright drives a full session and asserts zero calls |
| 8.4 | `confirm_booking` without a valid `gesture_token` is rejected |
| 8.5 | Double-submit with the same idempotency key produces **one** booking and two identical responses |
| 8.6 | Every decline/error/timeout test card renders a distinct, non-spinner UI state |
| 8.7 | Static denylist scan finds zero payment-provider identifiers in source, deps, or lockfiles |
| 8.8 | No card number is present in any log, trace, DB row, or audit entry — scan asserts it |
| 8.9 | `PENDING` older than TTL transitions to `EXPIRED` and releases the listing |
| 8.10 | `MOCK — NO REAL PAYMENT` banner is present and above the fold in the rendered App |
| 8.11 | Client-computed monthly payment matches server recomputation to the cent |
| 8.12 | Audit trail has one entry per transition with actor, timestamps, and gesture provenance |

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| "It's mocked, so shortcuts are fine" | This doc. The gateway is mocked; the lifecycle is not. Gates 8.1/8.5/8.9 don't care that it's fake. |
| Future refactor widens `confirm_booking` visibility | Gate 8.2 asserts resolved state each CI run; layer 3 (gesture token) survives the mistake anyway |
| Card data leaks into a trace | Gate 8.8 + P10's PII redaction; the App never posts raw card data to the host |
| Decline path never rendered until demo day | Deterministic test cards make it a normal test case; gate 8.6 requires all five |
| Someone adds `stripe` to requirements "just to look at the API" | Gate 8.7 fails the build |
