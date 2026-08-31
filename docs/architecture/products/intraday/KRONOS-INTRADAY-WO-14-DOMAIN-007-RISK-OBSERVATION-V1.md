# KRONOS Intraday V1 — WO-14 DOMAIN-007 Risk Observation

**Status:** Approved Architecture — source engineering gated on published WO-13 contracts

**Owner:** DOMAIN-007 / KRONOS Intraday adapter

**Contract:** `KRONOS-INTRADAY-DOMAIN-007-RISK-OBSERVATION-V1`

**Version:** `1.0.0`

**Authority:** `RISK_OBSERVATION_ONLY`

**Runtime Authority:** NONE

**Broker Authority:** NONE

## Purpose

WO-14 answers one question about an exact immutable WO-13 Trade Plan:

> If this already-constructed trade were taken, what observable downside
> exposure exists under the currently governed facts?

It reports facts and availability to the Sponsor. It does not approve, reject,
block, constrain or execute the trade.

## Operating sequence

```text
WO-12 analytical promotion
  -> WO-13 immutable Trade Plan
  -> execution-vehicle resolution where required
  -> WO-14 advisory Risk observation
  -> WO-15 final 5M Entry timing
  -> Sponsor PAPER / LIVE / IGNORE and actual quantity
```

WO-14 never blocks WO-15 solely because Risk is high, alerting, stale or
unavailable. A trust failure invalidates the Risk observation, not the trade.

## Exact input binding

The future input contract must bind:

- one exact immutable WO-13 Trade Plan and integrity;
- canonical subject and market family;
- direction and setup family;
- Entry Reference, Stop, Target and invalidation;
- structural risk distance, reward distance and Model R:R;
- field and aggregate geometry availability;
- WO-13 policy identity/version and analysis boundary;
- exact native instrument or active derivative contract and roll lineage;
- execution vehicle where required;
- canonical instrument economics and version;
- optional Sponsor capital-reference snapshot;
- optional Sponsor reference-band snapshot;
- optional authoritative portfolio/open-Risk snapshot;
- optional authoritative margin/account snapshot; and
- observation-methodology identity/version and evaluation boundary.

WO-14 validates but never reconstructs or changes WO-13 geometry.

## Output contract

The immutable observation may contain:

- observation identity, version, state and integrity;
- canonical subject, family, direction and setup;
- WO-13 plan identity/integrity;
- execution-vehicle identity and availability;
- `STRUCTURAL_RISK_PER_PRICE_UNIT`;
- `MONETARY_RISK_PER_TRADABLE_UNIT`;
- `REFERENCE_QUANTITY`, when governed inputs permit it;
- `LOSS_AT_STOP`, for a supplied reference or Sponsor-selected quantity;
- `CAPITAL_AT_RISK_PERCENTAGE`, when capital reference exists;
- `NOTIONAL_EXPOSURE`, when deterministically calculable;
- `EXISTING_OPEN_RISK` and `AGGREGATE_OPEN_RISK_AFTER_TRADE`, when authoritative;
- margin observations, when authoritative;
- unavailable fields and exact reasons;
- evidence freshness and input snapshot identities;
- observation boundary, timestamp and provenance.

It must not contain `TRADE_ALLOWED`, `TRADE_BLOCKED`, `RISK_APPROVED`,
`RISK_REJECTED`, `MAX_PERMITTED_QUANTITY`, `EXECUTE`, `PAPER_ALLOWED`,
`LIVE_ALLOWED` or `BROKER_ALLOWED`.

## State and alert vocabulary

| State | Meaning | Consequence |
| --- | --- | --- |
| `RISK_OBSERVED` | Required requested Risk facts were calculated | Facts displayed; no permission consequence |
| `RISK_ALERT` | A separately governed Sponsor reference band was crossed | Informational alert only; no veto |
| `RISK_UNAVAILABLE` | Requested Risk facts could not be calculated truthfully | Preserve reasons; no veto |

Initial V1 uses severity `UNCLASSIFIED`. `NORMAL`, `ELEVATED` and `HIGH` may be
introduced only by a separately governed threshold methodology. Until then
`RISK_ALERT` is not an ordinary producible state.

Trust-boundary operation failure uses `RISK_OBSERVATION_INVALID` provenance.
Where an outward result remains valid, its state is `RISK_UNAVAILABLE`. This
does not become permission or rejection.

## Geometry and arithmetic

Risk observes geometry. It never rewrites geometry.

For LONG, the independent arithmetic check is `Entry - Stop`; for SHORT it is
`Stop - Entry`. WO-13 remains authoritative for structural Risk distance and
Model R:R. WO-14 records disagreement as invalid observation evidence rather
than repairing the plan.

Geometry `COMPLETE` permits full observation only where economics are also
available. `PARTIAL` permits every truthfully calculable fact. `UNAVAILABLE`
may make the Risk observation unavailable. None means trade rejection.

## Cash Equity

```text
risk_per_share = abs(Entry - Stop)
loss_at_stop = risk_per_share * supplied_quantity
```

Geometry and Risk basis are stock-local. NIFTY has no Equity sizing, geometry
or loss-calculation authority.

## Index and execution vehicle

Underlying NIFTY/BANKNIFTY geometry is insufficient for monetary option Risk.
An exact governed execution vehicle must be resolved before WO-14 can observe
option-position loss exposure. Vehicle selection is outside WO-14 and remains
`POLICY_UNRESOLVED`; WO-14 cannot choose strike, expiry, CALL/PUT, option
structure or premium vehicle.

Until a vehicle exists, the underlying Trade Plan remains valid while
`OPTION_POSITION_RISK = UNAVAILABLE`.

## MCX

MCX observation binds the exact governed active futures contract and consumes:

- lot size;
- contract multiplier/unit economics;
- tick size and tick value where applicable;
- expiry and active binding;
- roll lineage; and
- instrument-economics version.

COMEX/NYMEX have no sizing authority. USDINR has no arithmetic authority unless
the governed MCX contract economics explicitly require an FX conversion.
`COMEX price * USDINR` is prohibited as MCX Risk. NATGAS remains held wherever
upstream commissioning remains held.

## Capital, quantity, margin and notional

`INTRADAY_RISK_CAPITAL_REFERENCE` is optional Sponsor configuration for context
only. It is not inferred from broker cash, available margin, NAV, net worth or
bank balance. Without it, capital percentage is unavailable while monetary
facts may remain observed.

No Risk fraction is frozen. If a future successor governs one:

```text
reference_risk_budget = capital_reference * reference_risk_fraction
reference_units = floor_to_tradable_unit(
    reference_risk_budget / monetary_risk_per_tradable_unit
)
```

The result is `REFERENCE ONLY`, not execution permission or maximum quantity.
Sponsor owns actual quantity.

Margin and structural capital-at-Risk are separate. Required/available margin
and utilisation may be observed from authoritative facts, but margin is not
the capital reference and has no V1 enforcement threshold. Notional exposure
is factual telemetry with no commissioned maximum.

## Portfolio, P&L and concentration

Existing open Risk and aggregate Risk after the proposed trade are published
only when authoritative portfolio facts exist. Missing facts make aggregate
Risk unavailable without veto.

No actual realised P&L, daily loss, win/loss count, actual R or execution fact
is inferred. LIVE facts require broker-confirmed fills or governed
Sponsor-attested execution; PAPER facts require governed simulation evidence.

V1 has no correlation engine, sector/concentration consequence, liquidity or
slippage model. Descriptive facts may be shown but have no veto authority.

## Model R:R and WO-15 exclusion

Model R:R is WO-13 context. WO-14 establishes no minimum and never moves Entry,
Stop or Target to improve it.

ATR extension/chase, 5M progression, trigger and timing are WO-15-only. Risk
facts may be shown alongside WO-15, but high, unavailable or stale Risk alone
cannot block timing evaluation.

## Freshness, persistence and supersession

Every observation binds all facts used, methodology `1.0.0`, evaluation
boundary, timestamp, provenance and integrity. Changed capital, portfolio,
margin, vehicle, economics or policy creates a new immutable observation.
Changed geometry first requires a new WO-13 plan.

Future persistence must be append-only with content-derived identities,
integrity validation, idempotent same-content retention, conflict rejection,
explicit-identity reload and no latest-file, mtime or symbol-only authority.

## Reuse and isolation

Reuse from Swing as principle:

- immutable plan binding;
- exact identity and integrity;
- fail-closed evidence behavior;
- Risk separate from geometry;
- Sponsor decision downstream;
- no broker authority;
- freshness/revalidation; and
- append-only persistence.

Reuse through adapter:

- WO-13 handoff;
- instrument economics;
- portfolio and account/margin fact interfaces;
- persistence patterns; and
- Browser projection patterns.

Do not copy Swing numerical thresholds, permission states or consequences,
quantity assumptions, concentration policy, margin assumptions or product
constraints. Swing remains governed by ADR-0013 and ADR-0015.

## Unresolved policy

The following remain unresolved without blocking factual observation:

- capital-reference amount and source configuration;
- reference Risk fraction and per-trade bands;
- aggregate-open-Risk, notional and margin reference bands;
- normal/elevated/high severity thresholds;
- concurrency, sector and concentration limits;
- quantitative correlation methodology;
- daily-loss and losing-trade references;
- liquidity/slippage model;
- Index option-selection methodology; and
- option multi-leg Risk methodology.

## Engineering gate

The architecture and factual methodology are ready. Source engineering is not
startable until the actual WO-13 Trade Plan/handoff contract is published and
stable and a separate source-engineering instruction is issued. No placeholder
geometry contract may be invented.

Runtime, Browser, real Risk observation, Provider access, WO-15 and broker work
remain unauthorized.

## Governance

This product record implements [ADR-0023](../../adr/ADR-0023-INTRADAY-DOMAIN-007-ADVISORY-RISK-OBSERVATION-BOUNDARY.md).
It is additive to [ADR-0022](../../adr/ADR-0022-INTRADAY-WO12-WO13-STEP31-TRADE-CONSTRUCTION-BOUNDARY.md)
and does not modify Swing ADR-0013/ADR-0015 semantics.
