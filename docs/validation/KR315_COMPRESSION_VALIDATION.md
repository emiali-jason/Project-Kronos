# KR-315 Compression Validation

**Status:** Active Validation Programme
**Engine:** KR-315 Compression Intelligence
**Scope:** Evidence collection only

## 1. Purpose

This validation programme measures whether Compression is functioning as:

- a quality filter; or
- a source of execution latency.

No conclusion is recorded from a single observation. This document does not approve calibration, threshold, architecture, or Pine changes.

## 2. Validation Question

When Compression is the Active Blocker during WATCH LONG or WATCH SHORT, does it prevent low-quality trades, or does it delay otherwise valid setups beyond useful execution?

## 3. Evidence Rules

- Record only values visible in screenshots or explicitly approved during review.
- Preserve blanks when a value is not visible.
- Do not infer BUY READY, BUY NOW, SELL READY, or SELL NOW from price movement alone.
- Do not change KR-315 thresholds based on this document.
- Do not treat one observation as proof of a defect.

## 4. Validation Record Template

| Field | Value |
|---|---|
| Instrument |  |
| Market |  |
| Date |  |
| Direction |  |
| Price when WATCH begins |  |
| Reason for WATCH |  |
| Compression state |  |
| Price when BUY READY appears |  |
| Price when BUY NOW appears |  |
| Maximum favourable excursion while WATCH |  |
| Time spent in WATCH |  |
| Did BUY READY occur? | YES / NO |
| Did BUY NOW occur? | YES / NO |
| Did the move fail before promotion? | YES / NO |
| Comments |  |

## 5. Future Metrics

These statistics are defined for future review only. They are not calculated in this document.

| Metric | Purpose |
|---|---|
| Average WATCH duration | Measures typical time spent waiting while Compression remains active |
| Median WATCH duration | Reduces distortion from outlier long waits |
| BUY READY conversion rate | Measures how often WATCH states eventually promote to BUY READY |
| BUY NOW conversion rate | Measures how often WATCH states eventually reach executable timing |
| Average move before BUY READY | Measures favourable movement that occurred before readiness |
| Average move before BUY NOW | Measures favourable movement that occurred before execution |
| Failed breakout rate | Measures how often compression-filtered setups fail before promotion |
| Successful breakout rate | Measures how often compression release precedes useful continuation |
| Compression as Active Blocker frequency | Measures how often Compression is selected as the highest-priority blocker |

## 6. Interpretation Guardrails

Compression may be working correctly even when it delays execution. The purpose of this programme is to separate useful selectivity from measurable latency through repeated evidence.

Engineering or calibration changes require repeated observations, documented metrics, and separate approval.

