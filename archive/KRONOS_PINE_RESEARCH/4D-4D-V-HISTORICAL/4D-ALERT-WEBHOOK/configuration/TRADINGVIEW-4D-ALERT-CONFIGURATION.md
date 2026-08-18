# KRONOS Swing V1 Main Slice 4D — Sponsor Alert Configuration

The public webhook receiver does not exist in 4D. Use a Sponsor-approved test
webhook placeholder only when runtime validation is authorized. Do not enter
credentials or authentication secrets.

## MCX

- Candidate: `research/swing/pine-publication/candidates/4D-MCX/KRONOS_FUTURES_V2_PINE_EVIDENCE_V1_1_ALERT_CANDIDATE.pine`
- Candidate SHA-256: `6bf7b7bd58a4bc9c839737a6ec0c258391b3a7c2a087c5cd333c5d8513eda73f`.
- Script input: paste the exact reported MCX 4D candidate SHA into
  **Validated 4D candidate SHA-256**.
- TradingView condition: candidate script → **Any alert() function call**.
- Frequency: **Once Per Bar Close**.
- Message: leave the runtime-generated message unchanged; do not construct or
  paste JSON manually.
- Expected payload: compact JSON for
  `KRONOS-SWING-V1-PINE-EVIDENCE-V1 / 1.1`, product `MCX`, role `CANDIDATE`.
- Boundary: confirmed realtime completed bar only.

## NSE

- Candidate: `research/swing/pine-publication/candidates/4D-NSE/KRONOS_NSE_V1_SR1_PINE_EVIDENCE_V1_1_ALERT_CANDIDATE.pine`
- Candidate SHA-256: `42f527dbd5c20b8c6bd0bdcf94b8635dbc76bd3fe85c76c83916aa8302542136`.
- Script input: paste the exact reported NSE 4D candidate SHA into
  **Validated 4D candidate SHA-256**.
- TradingView condition: candidate script → **Any alert() function call**.
- Frequency: **Once Per Bar Close**.
- Message: leave the runtime-generated message unchanged; do not construct or
  paste JSON manually.
- Expected payload: compact JSON for
  `KRONOS-SWING-V1-PINE-EVIDENCE-V1 / 1.1`, product `NSE`, role `CANDIDATE`.
- Boundary: confirmed realtime completed bar only.

For both products, compile and Add to chart first and confirm that the existing
workstation renders. Preserve exact compiler/runtime error text and line number
without speculative source edits.
