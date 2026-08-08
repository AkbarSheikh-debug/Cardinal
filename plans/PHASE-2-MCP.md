# PHASE 2 — MCP

**Owns:** the tool protocol layer. Three MCP servers, their schemas, their result-size discipline,
and their publication.

Everything the agent can *do* passes through here. Get the tool surface wrong and no amount of
prompt engineering above it recovers — the model will either not call the tool, call it with
garbage, or drown in its output.

---

## 1. Objective

Three MCP servers with prescriptive schemas, bounded results, and a published registry manifest —
usable both in-process by our agent and standalone by any MCP client.

## 2. Scope

### In
- `[MVP]` `marketplace-mcp` — search, get, availability, quote, tco inputs
- `[MVP]` `ui-mcp` — the A2UI rendering tools (implementation in P6; schemas here)
- `[MVP]` `booking-mcp` — booking tools (UI resources in P7, commerce in P8)
- `[MVP]` Dual transport: in-process `create_sdk_mcp_server` **and** standalone stdio/HTTP
- `[MVP]` Result-size caps and progressive disclosure
- `[SCALE]` Official MCP Registry manifest + submission
- `[SCALE]` Tool-level auth scopes for multi-tenant use

### Out
- Tool *implementations* that belong to later phases. P2 owns the contract; P5 fills `tco`, P6 fills
  `render_*`, P8 fills `confirm_booking`.

---

## 3. Why three servers, not one

| Server | Transport | Why separate |
|---|---|---|
| `marketplace-mcp` | in-proc + stdio | The only one that's genuinely reusable by third parties. Publishing it is the brief's optional-MCP-App credit, and it's the piece a partner dealer would host themselves. |
| `ui-mcp` | in-proc only | Tightly coupled to our A2UI catalog. Publishing it would be meaningless. |
| `booking-mcp` | **HTTP** | Must be HTTP because it serves `ui://` resources that the browser fetches through the host proxy (P7). Also the natural seam for a real dealer's booking system later. |

Splitting them also means a compromised or slow marketplace server can't take down checkout.

**Dual transport for `marketplace-mcp` is worth the small extra effort.** In-process via
`create_sdk_mcp_server` is fast and needs no subprocess; the stdio build is what makes it a *real*
MCP server you can point MCP Inspector or Claude Desktop at — which is a 30-second demo moment and
the thing that makes the registry submission honest.

---

## 4. Tool surface

### marketplace-mcp

| Tool | Returns | Notes |
|---|---|---|
| `search_cars` | `SearchPage` of **summaries** + total | Hard cap 20 per page. Never full records. |
| `get_listing` | one full `Listing` | Progressive disclosure: the model pulls detail only for candidates it's actually considering. |
| `check_availability` | windows for a date range | Rental adapters return real windows; dealer returns `ALWAYS`. |
| `get_quote` | priced terms | Duration-dependent. Separate from `get_listing` for a reason (P1 §3). |
| `compare_listings` | aligned field matrix, ≤5 ids | Saves the model five `get_listing` round trips and formats for `CompareTable`. |

### ui-mcp

| Tool | Notes |
|---|---|
| `render_progress` | interview state + reasoning trace |
| `render_results` | ranked list + weights + per-listing rationale |
| `render_detail` | one listing, optional `PowertrainExplainer` |
| `render_tco` | TCO comparison + break-even |
| `compose_surface` | the escape hatch. Validated server-side (P6 §4). |

### booking-mcp

| Tool | Visibility | Notes |
|---|---|---|
| `open_booking_form` | `["model","app"]` | Renders `ui://booking/form` |
| `open_checkout` | `["model","app"]` | Renders `ui://checkout/payment` |
| `submit_booking_draft` | `["app"]` | View-initiated only |
| `confirm_booking` | **`["app"]`** | **The model cannot see this tool.** Constitution rule II.2. |

`visibility: ["app"]` is the enforcement mechanism for the human-click invariant — not a prompt
instruction, not a permission callback that could be bypassed. The tool is simply absent from the
model's tool list. That's the difference between a guardrail and a request.

---

## 5. Tool schema design

Four rules, each of which measurably changes model behaviour:

**Descriptions are prescriptive, not descriptive.** "Call this when the user mentions a budget,
a date, or names a car category — do not call it before at least one requirement is known" beats
"Searches the car marketplace." Recent models reach for tools more conservatively; the trigger
condition belongs in the tool's own `description`, not only in the system prompt. Minimum three
sentences per tool, enforced by the gate.

**`strict: true` and `additionalProperties: false` everywhere.** A tool that silently accepts an
unknown field is a tool that silently does the wrong thing.

**Annotations carry scheduling information.** `readOnlyHint=True` on `search_cars`, `get_listing`,
`compare_listings` lets the harness parallelise them; `confirm_booking` is emphatically not
read-only.

**Enums over free strings.** `category: Literal[...]` rather than `category: str`. The model gets
the vocabulary from the schema instead of guessing, and typos become impossible rather than
merely unlikely.

---

## 6. Result-size discipline

The failure mode this prevents: a search returns 47 full listings, ~18k tokens land in context, the
next three turns cost 4× what they should, and by turn 12 the session is compacting away the
interview.

Rules:

- `search_cars` returns summaries capped at **20 items**, each **≤200 tokens**
- `get_listing` returns one full record, ≤800 tokens
- Any tool result over **100k characters** is written to a file and replaced by a path + preview
  (the SDK does this automatically; don't rely on it — cap first)
- Per-session token budget enforced in P9; P2's job is not to blow it

---

## 7. Registry publication `[SCALE]`

`marketplace-mcp` gets a manifest and a submission to the Official MCP Registry. Two reasons beyond
the brief's optional credit: it forces the standalone transport to actually work, and a published
server is a real artifact a startup can point at.

Manifest carries: name, description, version, transport, tool list with schemas, and an explicit
statement that the data is synthetic. **Do not publish a server that implies it fronts real
inventory.**

---

## 8. Exit gate

`scripts/gate_phase2.py`:

| # | Criterion |
|---|---|
| 2.1 | MCP Inspector connects to `marketplace-mcp` over stdio and lists all five tools |
| 2.2 | Every tool has a description ≥3 sentences containing an explicit "call this when" clause |
| 2.3 | Every input schema sets `additionalProperties: false` and `strict: true` |
| 2.4 | `search_cars` result for the broadest possible query is ≤20 items and ≤4000 tokens |
| 2.5 | `get_listing` result is ≤800 tokens |
| 2.6 | `confirm_booking` is absent from the tool list presented to the model (asserted by inspecting the SDK's resolved toolset, not by reading config) |
| 2.7 | In-process and stdio builds of `marketplace-mcp` return byte-identical results for a fixed query |
| 2.8 | Registry manifest validates against the registry schema (`[SCALE]`) |

Criterion 2.6 is the one that matters. Assert on the *resolved* toolset the SDK hands the model —
config files lie, resolved state doesn't.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Model under-calls tools (recent models are conservative) | Prescriptive "call this when" descriptions; raise `effort`; measure call rate in P9's evals rather than guessing |
| Three servers is operational overhead for a hackathon | In-process for two of them means one process in dev. Only `booking-mcp` is genuinely separate, and it has to be. |
| Tool schemas churn as P5/P6/P8 land | P2 freezes *signatures*; later phases fill bodies. A signature change after freeze needs a `DECISIONS.md` entry. |
| Standalone transport rots because nobody runs it | Gate 2.7 runs both and diffs them, every CI run. |
