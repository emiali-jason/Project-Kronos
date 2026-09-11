# WO-10 Futures-only product specification

## Current authority — ADR-0042

Status: Approved bounded engineering by direct Sponsor / EA authorization, 2026-09-11.

The earlier order quoted below remains preserved evidence. The current final Sponsor order commissions the ADR-0041 PULLBACK source and ADR-0042 advisory Risk composition. Risk magnitude, missing reference or missing monetary facts do not independently block Sponsor selection. Exact contract, temporal, lineage and executability authority is unchanged. All remaining current rules are recorded by ADR-0042 and the advisory Risk policy.

See [ADR-0042](../../adr/ADR-0042-WO10-ADVISORY-RISK-AND-FINAL-FUTURES-COMPOSITION.md) and [advisory Risk policy](KRONOS-INTRADAY-WO-10-ADVISORY-RISK-POLICY-V1.md).

## Preserved predecessor text

**Status:** Approved for bounded engineering — Sponsor / EA, 2026-09-11.

Governing successor: ADR-0039. The following is the exact accepted final engineering contract. Runtime operations and publication require separate authorization.

```text
KRONOS — WO-10
FUTURES-ONLY TRADE CONSTRUCTION, RISK & SPONSOR SELECTION
FINAL ENGINEERING ORDER

SPONSOR / EA AUTHORIZATION

WO-09 engineering, publication and runtime commissioning are complete.

WO-09 Sponsor operational acceptance remains intentionally PARKED until WO-10
is complete so the Sponsor can test WO-09 → WO-10 as one continuous journey.

The prior WO-10 architecture/preflight is accepted subject to the following
FINAL V1 scope:

WO-10 V1 IS FUTURES ONLY.

Options are deliberately deferred.

WO-10 is NOT a broker execution engine.

WO-10 DOES NOT calculate, enforce or reason about broker margin, available
margin, buying power, collateral, SPAN, pledge, funds or execution capital.

WO-10 remains:

TRADE CONSTRUCTION
+ FUTURES EXPRESSION
+ RISK-AWARE POSITION SIZING
+ EXECUTABILITY FACTS
+ SPONSOR DECISION SUPPORT
+ SPONSOR SELECTION

I authorize engineering under the bounded contract below.

NO PRODUCTION WO-10 OPERATION.
NO SPONSOR PRODUCTION ACCEPTANCE.
NO RUNTIME RESTART.
NO GIT STAGE / COMMIT / PUSH.

================================================================
1. PROSPECTIVE PROGRAMME AUTHORITY
================================================================

Create successor programme authority:

KRONOS-INTRADAY-PROSPECTIVE-PROGRAMME-V2

Prospective ownership:

WO-09
Governed Promotion & Active Readiness

WO-10
Futures Trade Construction, Risk & Sponsor Selection

WO-11
Position / Paper Observation / Lifecycle

WO-12
Opportunity Data & Research Ledger
+ Real XLSX Export
+ Sponsor Quantitative Analysis Details

WO-13
Notifications

WO-14
Trading Journal

WO-15
Portfolio

WO-16
Reports

Historical work-order numbering remains immutable.

Do NOT:

rewrite;

rename;

reinterpret;

delete;

migrate

historical records merely because prospective numbering changed.

Every new prospective record must bind:

programme identity;

programme version;

policy identity;

policy version;

policy checksum;

effective authority boundary.

Historical work-order numbers and prospective work-order numbers are separate
semantic epochs.

================================================================
2. SUCCESSOR ADR / OWNERSHIP
================================================================

Create a successor ADR:

ADR-0039
INTRADAY PROSPECTIVE WO09–WO16 PROGRAMME AUTHORITY

It must:

preserve every historical authority;

retire conflicting prospective authority only;

prohibit dual prospective ownership;

allow reuse of factual engines through explicit adapters;

make new prospective current pointers authoritative;

keep old pointers readable as historical evidence;

update ownership registry and programme roadmap.

Classify existing components:

WO-09 readiness
→ ADAPTED_INTO_NEW_WO / remains current

Old WO-10 E/I/M
→ HISTORICAL_ONLY
→ RETIRED_PROSPECTIVE_AUTHORITY

Old WO-11 analytical collation
→ HISTORICAL_ONLY
→ RETIRED_PROSPECTIVE_AUTHORITY

Old WO-12 V1/V2 promotion
→ HISTORICAL_ONLY

Old WO-13 construction records
→ HISTORICAL_ONLY

Old WO-13 geometry engine
→ ADAPTED_INTO_NEW_WO10

Old WO-14 Risk observations
→ HISTORICAL records preserved
→ factual formulas ADAPTED_INTO_NEW_WO10

Old WO-15 timing
→ future adaptation into prospective WO-11

Old WO-16 Sponsor decision
→ historical only
→ prospective Sponsor expression selection belongs to WO-10

Old WO-17 lifecycle
→ future adaptation into prospective WO-11

================================================================
3. WO-10 ENTRY GATE
================================================================

WO-10 accepts ONLY an exact-current WO-09:

BUY_NOW

or

SELL_NOW

with:

satisfied_count = 5

outstanding_count = 0

I1–I5 all SATISFIED

hard_gate = NONE

currentness = CURRENT

current pointer = exact readiness record

Require exact:

NextWoHandoff identity;

handoff integrity;

readiness identity;

readiness integrity;

policy identity/version/checksum;

programme identity;

canonical subject;

direction;

session;

analysis boundary;

WO-07F identity;

machine evidence;

visual evidence;

exact MCX contract/roll lineage where applicable.

Reject:

4/5;

NEAR_READY;

BUY_READY;

SELL_READY;

NO_FOCUS;

hard gated;

READINESS_UNAVAILABLE;

superseded;

foreign;

corrupt;

wrong-direction;

wrong-subject;

wrong-contract;

non-current.

================================================================
4. WO-09 → WO-10 CONSTRUCTION ADAPTER
================================================================

Implement:

exact-current WO-09 NextWoHandoff

→ WO10_FROM_WO09_CONSTRUCTION_ADAPTER_V1

→ existing governed setup-specific Intraday geometry engine

→ WO10_CANONICAL_TRADE_PLAN_V1

Do NOT fabricate an old WO-12/WO-13 handoff.

Do NOT duplicate geometry logic.

Reuse existing governed construction functions including the appropriate:

pullback geometry;

breakout geometry;

target population;

target constraints;

trade-plan arithmetic;

availability/warning semantics.

Historical WO-13 policy may remain named as the construction sub-policy.

New prospective WO-10 owns:

upstream lineage;

new record identity;

new persistence;

new current pointer;

new downstream authority.

================================================================
5. CANONICAL TRADE CONSTRUCTION
================================================================

WO-10 owns one canonical thesis before Futures mapping.

Retain:

Direction

Entry

Entry condition

Stop

Stop basis

Target

Target basis

Invalidation

Risk distance

Reward distance

Model R:R

Construction state

Unavailable/failure reason

Exact upstream lineage

Construction time/session

Freeze invariants:

Stop = thesis invalidation.

Stop may NOT be tightened to improve:

R:R;

position size;

Risk permission;

Sponsor preference.

LONG requires:

Target > Entry

SHORT requires:

Target < Entry

Equality fails.

No target shopping.

If canonical target is invalid, unavailable or non-forward:

TRADE_PLAN_UNAVAILABLE

Do NOT search another target merely to manufacture a viable R:R.

Model R:R is an OUTPUT.

No minimum R:R threshold exists in WO-10 V1.

R:R must not:

select Target;

repair Stop;

change Entry;

reverse direction.

================================================================
6. WO-10 V1 EXPRESSION SCOPE
================================================================

WO-10 V1 supports Futures only.

BUY_NOW
→ BUY FUTURE

SELL_NOW
→ SELL FUTURE

Sponsor may select:

SELECTED_FUTURE

or

NONE

Options remain explicit future capabilities:

OPTION_BUY =
NOT_COMMISSIONED_V1

OPTION_SELL =
NOT_COMMISSIONED_V1

Do NOT implement:

option chain;

option strike selection;

option expiry selection;

Black-Scholes;

Black-76;

IV;

Greeks;

Option Buy;

Option Sell;

option Risk;

option sizing;

option scenario R:R;

naked options;

defined-risk options.

Options are NOT a blocker to WO-10 V1.

================================================================
7. FUTURES CONTRACT SELECTION
================================================================

For NSE equity Futures, NIFTY Futures and BANKNIFTY Futures:

1. Load current complete instrument master.

2. Resolve exact canonical analytical subject.

3. Filter exact matching:
   NFO-FUT
   FUT

4. Require expiry strictly AFTER governed trading date.

5. Select unique minimum eligible expiry.

6. Require valid:
   exchange;
   symbol;
   provider identity;
   lot size;
   tick size;
   contract economics.

7. Reject duplicate/conflicting minimum-expiry candidates.

8. Bind:
   session;
   instrument-master identity;
   expiry;
   selector policy;
   canonical underlying identity.

9. On expiry date:
   current contract is ineligible from session open;
   select next listed eligible contract.

10. Never bridge contracts using symbol/token alone.

For MCX:

reuse existing exact active-futures authority.

NATGAS:

HELD.

WO-10 may not bypass commissioning.

================================================================
8. FUTURES MARKET SNAPSHOT
================================================================

Create immutable:

WO10_FUTURES_MARKET_SNAPSHOT_V1

For NSE equity/index:

acquire in ONE bounded full-quote operation:

UNDERLYING

and

EXACT SELECTED FUTURE.

For MCX exact-contract analysis:

acquire the exact governed Future contract.

Do NOT acquire Options.

Normalize and retain where available:

exchange_timestamp;

last_trade_timestamp;

last_price;

volume;

OHLC;

total_bid_quantity;

total_ask_quantity;

best_bid;

best_bid_quantity;

best_ask;

best_ask_quantity;

five bid depth levels;

five ask depth levels;

OI;

lot size;

tick size;

expiry;

instrument identity;

provider identity;

snapshot received time;

session identity;

field-level availability;

field-level provenance.

Provider token remains internal support evidence.

It is not the Sponsor-facing canonical identity.

================================================================
9. MARKET SNAPSHOT IDENTITY / PERSISTENCE
================================================================

Snapshot must bind:

programme identity;

WO-09 handoff identity;

readiness identity;

subject;

direction;

session;

instrument-master identity;

underlying identity where applicable;

exact Future contract;

selector policy;

Provider attribution;

request attribution;

observation timestamps;

all normalized fields;

freshness state;

integrity.

Require:

canonical serialization;

content-derived identity;

append-only retention;

idempotency;

conflict detection;

current pointer where appropriate;

supersession;

restart restoration.

Restored market snapshots are HISTORICAL evidence.

They must NOT automatically regain current/executable status after restart.

================================================================
10. FUTURES BASIS MAPPING
================================================================

For NSE equities / NIFTY / BANKNIFTY:

same governed snapshot must establish:

underlying_observed_price

and

future_observed_price.

Calculate:

basis =
future_observed_price
-
underlying_observed_price

Map canonical underlying geometry:

future_entry_raw =
underlying_entry + basis

future_stop_raw =
underlying_stop + basis

future_target_raw =
underlying_target + basis

Require cross-leg freshness and skew compliance.

Normalize to exact Future tick conservatively.

LONG:

Entry:
round up

Stop:
round down

Target:
round down

SHORT:

Entry:
round down

Stop:
round up

Target:
round up

After tick normalization recalculate:

Future risk distance;

Future reward distance;

Future Model R:R.

Canonical underlying geometry remains immutable.

Mapped Future levels do NOT replace the underlying thesis.

Underlying invalidation remains thesis authority.

For MCX exact-contract local geometry:

basis =
NOT_APPLICABLE

Use direct contract-local geometry.

Do NOT manufacture basis = 0.

================================================================
11. FUTURES EXPRESSION RECORD
================================================================

Create immutable:

WO10_FUTURE_EXPRESSION_V1

Bind:

canonical Trade Plan identity;

market snapshot identity;

direction;

exact Future contract;

expiry;

lot;

tick;

basis where applicable;

mapped Future Entry;

mapped Future Stop;

mapped Future Target;

mapped Future invalidation relationship;

Future Risk distance;

Future Reward distance;

Future Model R:R;

OI;

Delta OI where available;

volume;

bid;

ask;

spread;

depth;

freshness;

executability;

Risk evidence;

Pros/Cons version.

================================================================
12. OI
================================================================

Retain current Future OI when available.

No OI threshold exists in V1.

OI is Sponsor-visible quantitative evidence.

OI does NOT:

change direction;

change Entry;

change Stop;

change Target;

change readiness;

change R:R.

Missing OI does not automatically make the Future non-executable unless the
governed provider/identity contract requires it.

================================================================
13. DELTA OI
================================================================

Use:

SESSION_FIRST_OBSERVED_OI_BASELINE_V1

The first lawful current full quote for the exact Future contract in the
governed session creates the immutable OI baseline.

First observation:

Delta OI =
UNAVAILABLE

Later same-session/current observations:

delta_oi =
current_oi - baseline_oi

Require same:

exact Future contract;

Provider;

session;

instrument-master lineage.

Persist:

baseline identity;

baseline integrity;

baseline observation time.

Never calculate Delta OI across:

different contract;

roll;

different session;

different Provider lineage.

After restart:

baseline may restore historically;

current OI must be reacquired before current Delta OI is calculated.

If baseline unavailable/stale:

DELTA_OI_SESSION_BASELINE_UNAVAILABLE

================================================================
14. FRESHNESS
================================================================

Use:

WO10_MARKET_AND_DECISION_FRESHNESS_V1

WO-09 NOW:

must be CURRENT;

same governed session;

no more than 5 minutes since first_five_of_five_at.

Canonical Trade Plan:

same current WO-09 identity/session;

no more than 5 minutes since construction.

Underlying/Future full quote:

exchange timestamp no older than 30 seconds at snapshot completion.

Bid/ask/depth:

same 30-second TTL.

OI:

same current quote;

30-second Sponsor-decision TTL.

Sponsor selection:

must occur within 30 seconds of snapshot completion.

Cross-leg skew:

maximum 5 whole seconds between earliest/latest exchange timestamps.

Session:

validate through DOMAIN-008 at acquisition and Sponsor selection;

must be OPEN.

Expiry:

strictly after governed trading date.

Instrument master:

complete snapshot for same governed trading date;

expires at session close.

Canonical storage:

timezone-aware UTC.

Market/session evaluation:

Asia/Kolkata.

Do not claim sub-second market precision unsupported by Provider timestamp
resolution.

Reacquisition creates a new immutable snapshot/comparison.

Restored dynamic quotes remain historical until reacquired.

================================================================
15. FUTURES ACQUISITION OPERATION
================================================================

Create:

WO10_ACQUISITION_OPERATION_V1

For one exact-current 5/5 candidate:

1. Validate current daily instrument master.

2. Resolve canonical subject.

3. Resolve exact Future.

4. Issue ONE batched full-quote request:
   underlying + Future.

For MCX exact-contract local geometry:
quote the exact Future as required by the governed contract.

5. Normalize.

6. Validate.

7. Calculate:
   spread;
   basis where applicable;
   OI;
   Delta OI where baseline exists.

8. Persist immutable snapshot.

Normal physical quote requests:

1

Maximum:

2 only if current daily instrument master itself must first be lawfully
acquired.

Automatic retries:

0

Request timeout:

7 seconds

Respect Provider rate limits.

Every request must be attributed to the acquisition operation.

Provider failures remain explicit.

No opportunistic retries.

No contract widening.

No alternate expiry shopping.

================================================================
16. EXECUTABILITY
================================================================

Use bounded V1 states:

EXECUTABLE

UNAVAILABLE

STALE

MARKET_NOT_EXECUTABLE

NOT_COMMISSIONED

Hard factual failures include:

unresolved instrument;

conflicting instrument identity;

wrong contract;

expired/ineligible contract;

session closed;

required quote missing;

required quote stale;

invalid lot;

invalid tick;

invalid contract economics;

missing positive actionable bid/ask;

bid > ask;

zero/invalid actionable price;

cross-leg skew exceeded;

required Risk permission unavailable for Sponsor selection.

Locked market:

bid = ask

is valid.

Do NOT introduce V1 thresholds for:

spread;

volume;

OI;

Delta OI;

depth;

slippage.

Show these quantitatively.

Do not classify:

GOOD;

BAD;

HIGH;

LOW;

WIDE;

TIGHT

without later governed thresholds.

================================================================
17. WO-10 RISK FACT
================================================================

Create:

WO10_RISK_FACT_V1

Reuse existing lawful WO-14 factual arithmetic where possible.

Do NOT reinterpret old WO-14 records.

Risk Fact owns factual:

risk per unit;

risk per lot;

reward per unit;

reward per lot;

Future R:R;

configured per-trade Risk budget;

remaining aggregate Risk capacity;

remaining product Risk capacity;

configured lot caps;

existing open Risk inputs;

availability/currentness of Risk inputs.

WO-10 Risk Fact has no authority to rewrite geometry.

================================================================
18. WO-10 RISK PERMISSION
================================================================

Create:

WO10_RISK_PERMISSION_V1

Permission states:

APPROVED

CONSTRAINED

REJECTED

UNAVAILABLE

Risk Permission may own:

maximum_permitted_lots;

constraint identities;

ordered reason codes.

It may NOT change:

direction;

Entry;

Stop;

Target;

Invalidation;

WO-09 readiness;

WO-07F;

Future contract identity.

================================================================
19. NO BROKER MARGIN AUTHORITY
================================================================

WO-10 V1 is NOT a broker execution/admission engine.

Do NOT calculate or gate on:

broker margin;

SPAN;

exposure margin;

available broker margin;

available funds;

buying power;

pledged collateral;

cash balance;

broker RMS;

margin shortfall;

execution capital availability.

Do NOT call broker margin APIs.

Do NOT store a margin-per-lot permission field.

Do NOT reject/constrain a trade because broker margin is unknown.

If contract notional is useful for information, it may be retained as a
non-permission factual value, but it must not act as an execution/margin gate.

================================================================
20. RISK CONFIGURATION
================================================================

Do NOT invent Risk percentages or capital assumptions.

Support configured:

currency = INR

maximum_monetary_risk_per_trade

maximum_aggregate_open_risk

existing_open_risk

optional product maximum Risk

existing_product_risk

optional product maximum lots

optional global maximum lots

source identity

integrity

effective timestamp

expiry/currentness

Capital reference may be retained as optional contextual information if
configured, but is NOT required for broker-margin admission.

No default:

capital;

Risk percentage;

lot count.

If required Risk config is absent/stale/inconsistent:

Risk Permission =
UNAVAILABLE

================================================================
21. FUTURES POSITION SIZING
================================================================

Use Risk-only sizing.

Calculate:

risk_per_unit =
abs(mapped_future_entry - mapped_future_stop)

risk_per_lot =
risk_per_unit
× lot_size
× contract_multiplier

remaining_aggregate_risk =
max(
  0,
  maximum_aggregate_open_risk
  - existing_open_risk
)

Where product Risk limit exists:

remaining_product_risk =
max(
  0,
  product_risk_limit
  - existing_product_risk
)

If no product Risk limit is configured:

do not manufacture one.

Core Risk capacity:

risk_capacity_amount =
minimum of all APPLICABLE configured Risk constraints.

maximum_risk_permitted_lots =
floor(
  risk_capacity_amount
  / risk_per_lot
)

Then apply ONLY configured optional lot caps:

configured_product_max_lots

configured_global_max_lots

Final:

maximum_permitted_lots =
minimum of:
maximum_risk_permitted_lots
and any applicable configured lot caps.

Do NOT include:

margin_capacity_lots;

broker capital capacity;

available margin.

Invalid/zero Risk geometry:

UNAVAILABLE.

Complete facts where one lot exceeds all lawful Risk capacity:

REJECTED.

At least one lot permitted but a configured aggregate/product/lot cap reduces
the primary per-trade capacity:

CONSTRAINED.

At least one lot permitted and no secondary configured constraint reduces the
primary per-trade capacity:

APPROVED.

================================================================
22. SPONSOR QUANTITY
================================================================

Sponsor may choose any whole-lot quantity:

1

through

maximum_permitted_lots

or:

NONE

Sponsor is never forced to take maximum permitted lots.

Retain separately:

maximum_permitted_lots

sponsor_selected_lots

Do NOT create:

actual activated quantity;

actual executed quantity;

fill quantity.

Those belong to WO-11.

================================================================
23. FUTURES PROS / CONS
================================================================

Governed structural Pros:

LINEAR_PRICE_EXPOSURE

NO_OPTION_TIME_DECAY

DIRECT_FUTURES_EXPRESSION_OF_GOVERNED_THESIS

For basis-mapped NSE/index Futures additionally expose:

BASIS_MAPPED_THESIS

Governed structural Cons:

LEVERAGED_LOSS_EXPOSURE

GAP_EXPOSURE

BASIS_RISK
where applicable.

Do NOT list:

MARGIN_REQUIRED

as a WO-10 Risk/executability criterion.

If desired it may appear only as a general educational characteristic of
Futures, but not as a calculated Sponsor admission fact.

Candidate-specific Sponsor output must prioritize exact numbers:

Future price;

bid;

ask;

absolute spread;

percentage spread;

depth;

volume;

OI;

Delta OI;

basis;

mapped Entry;

mapped Stop;

mapped Target;

Risk per lot;

Reward per lot;

Future R:R;

maximum permitted lots;

freshness;

Risk state;

executability state.

No unsupported qualitative labels.

================================================================
24. SPONSOR COMPARISON
================================================================

WO-10 V1 has one commissioned expression:

FUTURE

Show Options as:

OPTION BUY
NOT_COMMISSIONED_V1

OPTION SELL
NOT_COMMISSIONED_V1

Do not hide their capability state if the presentation architecture includes
expression capability.

Sponsor comparison must show:

canonical thesis;

underlying geometry;

exact Future;

Future market facts;

basis mapping;

Risk;

permitted size;

executability;

freshness;

Pros;

Cons;

Option capability state.

Browser must project persisted authority.

Browser must NOT calculate:

basis;

geometry;

R:R;

Risk;

size;

executability.

================================================================
25. SPONSOR SELECTION
================================================================

V1 values:

SELECTED_FUTURE

NONE

Options are not selectable.

Sponsor selection binds:

programme identity;

WO-09 identity;

canonical Trade Plan;

Future snapshot;

Future expression;

Risk Fact;

Risk Permission;

executability;

freshness;

Pros/Cons policy;

maximum permitted lots;

Sponsor-selected lots;

or NONE;

Sponsor action timestamp;

integrity.

Sponsor selection is NOT:

activation;

PAPER;

LIVE;

position;

fill;

broker order;

portfolio exposure;

P&L.

================================================================
26. WO-11 HANDOFF
================================================================

Only:

SELECTED_FUTURE

may create:

WO10_SELECTED_TRADE_HANDOFF_V1

Bind:

programme identity;

WO-10 selection identity;

WO-09 identity;

WO-07F lineage;

subject;

direction;

canonical Trade Plan identity;

underlying Entry;

Stop;

Target;

Invalidation;

underlying R:R;

Future snapshot identity;

exact Future contract;

exchange;

Provider identity;

expiry;

lot;

tick;

basis where applicable;

mapped Future Entry;

mapped Future Stop;

mapped Future Target;

Future R:R;

Risk Permission identity/state;

maximum permitted lots;

Sponsor-selected lots;

executability identity/state;

freshness;

Sponsor selection timestamp;

integrity.

NO:

activation;

PAPER/LIVE;

fill;

position;

actual executed quantity;

P&L;

broker authority.

NONE creates no WO-11 trade handoff.

================================================================
27. WO-12 RESEARCH FORWARD
================================================================

Do NOT implement WO-12.

Retain enough prospective WO-10 evidence for WO-12 to later answer:

how many 5/5 NOW opportunities reached WO-10;

how many produced a lawful Future;

how many failed construction;

how many failed instrument resolution;

how many became stale;

how many were Risk APPROVED;

CONSTRAINED;

REJECTED;

UNAVAILABLE;

how many Sponsor selected FUTURE;

how many Sponsor selected NONE;

Risk per lot;

maximum permitted lots;

Sponsor-selected lots;

spread;

volume;

OI;

Delta OI;

basis;

Future R:R;

unavailable reason;

timestamps;

later WO-11 lifecycle linkage.

Preserve ONE opportunity denominator.

================================================================
28. BROWSER — COMPACT SPONSOR VIEW
================================================================

Implement Sponsor-facing projection.

Show at minimum:

instrument;

direction;

WO-09:
BUY_NOW / SELL_NOW 5/5;

canonical Entry;

Stop;

Target;

Invalidation;

underlying R:R;

exact Future contract;

expiry;

Future current price;

bid;

ask;

spread;

volume;

OI;

Delta OI;

basis;

mapped Future Entry;

mapped Future Stop;

mapped Future Target;

Future Risk per lot;

Future Reward per lot;

Future R:R;

Risk state;

maximum permitted lots;

executability;

freshness;

Pros;

Cons;

Sponsor lot selector;

SELECT FUTURE;

NONE;

VIEW ANALYSIS DETAILS.

Do not overload the compact card.

Important Sponsor facts first.

Full evidence on click.

================================================================
29. ANALYSIS DETAILS
================================================================

Support at minimum:

A. WHAT WO-09 PROMOTED

B. CANONICAL TRADE CONSTRUCTION

C. FUTURES CONTRACT & MARKET SNAPSHOT

D. BASIS / FUTURES MAPPING

E. RISK & POSITION SIZE

F. EXECUTABILITY / FRESHNESS

G. PROS & CONS

H. SPONSOR SELECTION

I. TECHNICAL EVIDENCE

Expose numbers and authority.

Do not replace numbers with unsupported adjectives.

================================================================
30. PERSISTENCE
================================================================

Implement separate immutable truth families:

WO10_FUTURES_MARKET_SNAPSHOT_V1

WO10_CANONICAL_TRADE_PLAN_V1

WO10_FUTURE_EXPRESSION_V1

WO10_RISK_FACT_V1

WO10_RISK_PERMISSION_V1

WO10_SPONSOR_COMPARISON_V1

WO10_SPONSOR_SELECTION_V1

WO10_SELECTED_TRADE_HANDOFF_V1

Require:

canonical serialization;

content-derived identities;

integrity;

append-only records;

atomic prospective current pointers;

idempotency;

conflict rejection;

supersession;

restart restoration;

historical retention.

New market data must never rewrite historical selection evidence.

Superseded WO-09 authority must remove prospective currentness from dependent
WO-10 records without deleting them.

================================================================
31. RESTORATION
================================================================

On restart:

restore historical WO-10 records;

restore Sponsor selections;

restore configuration identities;

restore OI session baseline evidence where still session-valid;

do NOT restore old quotes as current;

do NOT restore stale executability as executable;

do NOT automatically rerun acquisition;

do NOT automatically rerun Risk;

do NOT automatically create Sponsor selection;

do NOT automatically create WO-11 handoff beyond already persisted lawful
handoff truth.

Dynamic market data must be reacquired for current decision authority.

================================================================
32. HISTORICAL COMPATIBILITY
================================================================

Every new WO-10 record must bind:

KRONOS-INTRADAY-PROSPECTIVE-PROGRAMME-V2

Historical:

WO-10;

WO-11;

WO-12;

WO-13;

WO-14;

WO-15;

WO-16;

WO-17

records remain readable under historical identities.

Do NOT rewrite their bytes.

Do NOT repoint old current pointers into prospective namespaces.

================================================================
33. REQUIRED DOCUMENTATION
================================================================

Create/update:

ADR-0039 prospective WO09-WO16 programme;

ENGINE_OWNERSHIP where required;

ownership registry;

knowledge base;

programme roadmap;

WO-10 Futures-only product specification;

WO-10 interface contract;

historical work-order-number compatibility document;

WO-11 selected-trade handoff document;

WO-12 research-forward contract;

WO-10 Futures snapshot policy;

WO-10 freshness policy;

WO-10 Risk Permission policy;

WO-10 Sponsor Selection policy;

ADR index/README as required.

Do NOT create Option pricing/IV/Greeks policy documents for V1.

================================================================
34. ENGINEERING QUALIFICATION
================================================================

Use controlled deterministic fixtures only.

Do NOT manufacture a production 5/5 candidate.

Test at minimum:

WO-09 exact-current 5/5 intake PASS;

4/5 rejected;

3/5 rejected;

hard gate rejected;

superseded readiness rejected;

wrong pointer rejected;

wrong direction rejected;

wrong subject rejected;

BUY_NOW;

SELL_NOW;

NSE equity Future;

NIFTY Future;

BANKNIFTY Future;

MCX Future;

NATGAS HELD;

current eligible expiry;

expiry-day roll;

duplicate Future contract conflict;

missing Future contract;

invalid lot;

invalid tick;

same-snapshot underlying/Future binding;

basis mapping;

LONG tick rounding;

SHORT tick rounding;

forward target invariant;

no target shopping;

invalid construction;

Risk/reward/R:R recalculation;

OI available;

OI unavailable;

OI session baseline creation;

first Delta OI unavailable;

later Delta OI;

cross-roll Delta OI rejected;

fresh snapshot;

stale snapshot;

cross-leg skew failure;

session closed;

expired Future;

missing bid;

missing ask;

bid > ask;

locked market valid;

Risk config available;

Risk config missing;

APPROVED;

CONSTRAINED;

REJECTED;

UNAVAILABLE;

one lot exceeds Risk budget;

aggregate Risk constraint;

product Risk constraint;

optional lot cap;

Sponsor 1 lot;

Sponsor less than maximum;

Sponsor maximum;

invalid zero quantity;

invalid above-maximum quantity;

SELECTED_FUTURE;

NONE;

Option Buy NOT_COMMISSIONED_V1;

Option Sell NOT_COMMISSIONED_V1;

no Options code introduced;

selection persistence;

idempotency;

conflict rejection;

supersession;

restart restoration;

restored quotes remain historical;

Browser projection-only;

WO-11 handoff only from SELECTED_FUTURE;

NONE produces no handoff;

no activation;

no position;

no fill;

no broker authority;

no broker margin authority.

================================================================
35. REGRESSION QUALIFICATION
================================================================

Run:

dedicated WO-10;

affected Intraday;

Opening;

MCX;

WO-06H/live-shadow;

WO-07E;

WO-07F;

WO-09;

Provider/market-data;

instrument/active-derivative;

construction/geometry;

Risk factual arithmetic;

Browser/server;

persistence/restoration;

full active repository;

Python compile/static;

git diff --check INCLUDING new/untracked paths;

document QA;

changed-scope secret scan.

Any staged-diff check used for new files must include ALL candidate files so
the previous WO-09 untracked-file whitespace issue cannot recur.

================================================================
36. CURRENT DATA / PRODUCTION SAFETY
================================================================

Engineering qualification must remain isolated.

Do NOT:

run production WO-09 evaluation;

manufacture production BUY_NOW/SELL_NOW;

run production WO-10;

acquire production Future data;

create production snapshots;

create production Trade Plans;

create production Risk Permission;

record production Sponsor selection;

create WO-11 production handoff;

run PAPER/LIVE;

create positions;

create observations;

perform broker/trading operations.

Provider state must not be changed.

================================================================
37. RUNTIME
================================================================

Do NOT restart runtime.

Current runtime is expected to remain on the existing published WO-09
revision until a later explicit WO-10 runtime-load authorization.

Do not modify Provider authentication/connectivity merely to qualify WO-10.

================================================================
38. GIT
================================================================

DO NOT:

stage;

commit;

push;

amend;

rebase;

merge;

tag.

After successful qualification:

freeze exact candidate;

compute every candidate file SHA-256;

compute candidate manifest SHA-256;

return to Sponsor/EA.

================================================================
39. REQUIRED RETURN
================================================================

Return:

WO_10_FUTURES_ONLY_ENGINEERING_CANDIDATE =
PASS / FAIL / BLOCKED

A. CONTRACT

programme identity/version;

WO-10 policy identities/checksums;

successor ADR;

effective authority boundary;

historical compatibility;

Futures-only V1 scope;

explicit no-broker-margin boundary.

B. IMPLEMENTATION

WO-09 adapter;

construction reuse;

canonical Trade Plan;

Future selector;

market snapshot;

basis mapping;

OI;

Delta OI;

freshness;

acquisition;

Future expression;

Risk Fact;

Risk Permission;

Risk-only sizing;

executability;

Pros/Cons;

Sponsor selection;

WO-11 handoff;

persistence;

restoration;

Browser;

Analysis Details.

C. PRODUCT RESULTS

NSE equity;

NIFTY;

BANKNIFTY;

MCX;

NATGAS HELD.

D. RISK / SIZING

risk per lot;

Risk-only maximum permitted lots;

APPROVED;

CONSTRAINED;

REJECTED;

UNAVAILABLE;

confirm broker margin is NOT calculated or used.

E. OPTIONS

OPTION_BUY =
NOT_COMMISSIONED_V1

OPTION_SELL =
NOT_COMMISSIONED_V1

Option pricing code introduced =
NO

IV/Greeks code introduced =
NO

F. QUALIFICATION

all dedicated/regression test counts;

full repository;

compile/static;

unstaged and complete-candidate diff check;

document QA;

secret scan.

G. PRESERVATION

WO-06H;

WO-07E;

WO-07F;

WO-09;

98/98;

NATGAS;

historical authorities;

production evidence.

H. CANDIDATE

exact path count;

modified/new/deleted;

diff;

every SHA-256;

candidate manifest SHA-256;

branch;

HEAD;

origin;

ahead/behind;

worktree;

staged;

untracked.

I. RUNTIME / PROVIDER

runtime PID;

loaded revision;

Provider state;

runtime transitions initiated;

Provider acquisitions initiated;

production operations initiated.

J. BLOCKERS

GENUINE_ENGINEERING_BLOCKER =
NONE

or exact bounded blocker.

================================================================
40. STOP
================================================================

STOP AFTER ENGINEERING CANDIDATE QUALIFICATION.

DO NOT STAGE.

DO NOT COMMIT.

DO NOT PUSH.

DO NOT RESTART.

DO NOT RUN PRODUCTION WO-10.

DO NOT RUN SPONSOR ACCEPTANCE.

WO-09 + WO-10 Sponsor acceptance remains deferred until the WO-10 candidate is
published and loaded.

Return to Sponsor/EA.
```
