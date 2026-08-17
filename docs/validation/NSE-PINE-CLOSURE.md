# KRONOS NSE Pine Closure

**Programme:** KRONOS NSE Pine / NSE Swing Pine validation and development track

**Status:** CLOSED

**Closure date:** 2026-08-17

## Production Disposition

| Item | Final status |
|---|---|
| Current NSE Production Pine | `KRONOS_NSE/source/KRONOS_NSE.pine` |
| Production identity | `KRONOS NSE / 0.6.0 / build 0005 / Pine v6` |
| Production lineage | NSE-V1-SR1 |
| Production SHA-256 | `802f21a33ec51279758732c8c1b08656691079077b508ac3b76c465242cb2a76` |
| Accepted NSE-V1-SR1 SHA-256 | `33ddbdd416d905bf4cb925d45d08d9d4efccfe6db969b668d5101164c96b48f2` |
| Difference from SR1 | Production metadata, identity, and presentation only |
| Analytical difference from SR1 | NONE |
| Threshold difference from SR1 | NONE |
| Previous NSE Production | NONE |
| Working candidate | `KRONOS_NSE_V1_CANDIDATE/source/KRONOS_NSE_V1_CANDIDATE.pine` — PRESERVED |
| SR1 checkpoint | `KRONOS_NSE_V1_CHECKPOINTS/NSE-V1-SR1/source/KRONOS_NSE_V1_SR1.pine` — PRESERVED |
| TradingView Pine v6 compile | PASS; no compiler errors or warnings; within token limit |
| Add-to-chart | PASS |

Representative 1H validation passed for SBIN, INFY, RELIANCE, SUNPHARMA, HINDALCO, MUTHOOTFIN, KAYNES, NIFTY, and BANKNIFTY. NSE 1H remains readiness-applicable. Daily and 4H remain readiness NOT APPLICABLE. BUY READY and SELL READY remain reachable; BUY NOW and SELL NOW remain unavailable in NSE V1.

## Frozen Qualification and Findings

- NSE-A, NSE-B, NSE-C, and NSE-D: APPROVED / HISTORICAL.
- Approved analytical universe: 91 equities plus NIFTY and BANKNIFTY — 93/93 PASS.
- Unknown NSE subjects: REJECTED.
- Options: EXCLUDED.
- Underlying-first routing: PASS.
- Opportunity: mandatory and independent.
- Weak Momentum, Compression, ordinary Review adversity, and contradictory Reference Alignment: readiness reducing.
- Hard Barrier: explicit veto only.
- NIFTY and BANKNIFTY Reference Alignment: NOT APPLICABLE.
- Confidence and Quality: explanatory only.
- Need: canonical.
- Historical Week-1 results and evidence: PRESERVED / UNCHANGED.
- SBI CPR investigation: CLOSED — EXPECTED BEHAVIOUR. NSE and MCX KR-280 methodology are identical; no SBI correction is required.
- NSE-T01 — Unsupported NSE Surface CPR Fallback: DEFERRED MAINTENANCE. Impact on the approved 93 subjects: NONE.

## Closure Basis

The NSE Production Pine is incorporated into the integrated Swing V1 probable-by-probable review workflow:

```text
Native Probable
  -> Sponsor TradingView chart
  -> Chart Analyst / governed Visual Evidence
  -> KRONOS Layer-2
  -> Readiness
```

Pine remains an evidence source where applicable. Closure does not imply NSE Pine failure, an analytical defect, invalidation of NSE-A/B/C/D, invalidation of the 93/93 qualification, or invalidation of historical Week-1 evidence. It creates no new governance programme.

Integrated Swing Visual Review continues. Future NSE Pine refinement is permitted only when supported by evidence from actual Swing operation or a separately approved product requirement.

MCX is separate, already closed, and unchanged. Its Production SHA-256 remains `85ccc53181607b8c82d40dc230cd1025f99be1e876d1d8278119ade32eed9bf8`.
