# WO-10 advisory Risk policy V1

Status: Approved bounded engineering under [ADR-0042](../../adr/ADR-0042-WO10-ADVISORY-RISK-AND-FINAL-FUTURES-COMPOSITION.md).

Active WO10 policy version: 1.1.0. Risk is factual/advisory only. Permission-oriented historical 1.0.0 records remain historical; no new permission record can be emitted.

| Fact | Exact rule |
|---|---|
| Risk per lot | mapped Risk distance × exact contract lot × authoritative monetary multiplier |
| Reward per lot | mapped Reward distance × same economics |
| Reference | optional sealed INR amount, source, effective time and expiry; no default |
| Reference lots | floor(reference / Risk per lot), advisory only |
| Selected quantity | positive whole lots; no Risk cap |
| Selected monetary Risk | Risk per lot × selected lots |
| Difference | selected Risk − reference |
| Percentage | difference / nonzero reference × 100 |

An explicitly zero reference has no computable percentage. Missing monetary economics has no computable Risk/lot. Neither is a Risk veto. Missing/stale/invalid/superseded reference is explicitly unavailable. Market/lineage hard gates remain intact.

WO10_RISK_FACT_V1 retains expression binding, unit/lot Risk and reward, R:R, economics source and reasons. WO10_RISK_REFERENCE_V1 contains currency, risk_reference_amount, source_identity, effective_at and expires_at; the envelope supplies config identity/integrity. WO10_RISK_ADVISORY_V1 retains fact/reference identities, selected quantity/Risk, differences, warning and evaluation time. No maximum-permitted quantity or APPROVED/CONSTRAINED/REJECTED trade permission exists.

Warning states: WITHIN_REFERENCE, ABOVE_REFERENCE, REFERENCE_NOT_CONFIGURED, RISK_FACT_UNAVAILABLE; QUANTITY_NOT_SELECTED is the explicit pre-choice state. ABOVE_REFERENCE is red and text-labelled, includes exact numbers, and leaves SELECT FUTURE enabled when independent trade authority is valid.

## Product matrix

| Product | Contract/monetary capability | Current monetary source disposition |
|---|---|---|
| NSE equity Future | exact NFO master/lot and INR quotation | supported |
| NIFTY Future | exact NFO master/lot and INR quotation | supported |
| BANKNIFTY Future | exact NFO master/lot and INR quotation | supported |
| CRUDE | exact active MCX contract; independent monetary port | missing monetary authority is advisory unavailable |
| GOLDM | exact active MCX contract; independent monetary port | missing monetary authority is advisory unavailable |
| SILVERM | exact active MCX contract; independent monetary port | missing monetary authority is advisory unavailable |
| COPPER | exact active MCX contract; independent monetary port | missing monetary authority is advisory unavailable |
| NATGAS | identity supported; commissioning HELD | no WO10 selection |

Provider master and active-derivative metadata carry lot, tick, expiry and exact identity, but do not establish MCX quotation/contract units, tick monetary value or INR-per-point multiplier. No retained production Wo14 economics family was established during this correction. Fixture economics test the typed consumer; they are never production source evidence. No multipliers are imported from memory or international visual references.
