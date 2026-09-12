# KRONOS Intraday WO-12 Local Research Publication V1

Policy: `KRONOS-INTRADAY-WO12-LOCAL-RESEARCH-PUBLICATION-POLICY / 1.0.0`

Policy checksum: `8de6a6487449e1deee240b0ce6636456bd6f16f149ba787b86d9172949d64af1`

Workbook: `KRONOS-INTRADAY-RESEARCH-WORKBOOK-V1 / 1.0.0`

This product publishes one verified local monthly XLSX from compact retained
Intraday evidence. It is research-only and has no trading, Provider, Review,
Chart Analyst, reconciliation, selection, execution or broker authority.

`opportunity_id` is the stable Sponsor-readable key and the first column of
`Opportunities`. `opportunity_identity` is a separate authoritative machine
identity. Both appear in each detail sheet. An opportunity begins at the
earliest retained admitted Probables event. Only a retained terminal WO-11
track followed by a later admitted event can establish another same-session
opportunity. All downstream stage identities remain exact source lineage.

The local root is `/Users/imranali/Documents/Project-KRONOS/Statistics/Intraday`.
The filename is `KRONOS_Intraday_Research_YYYY_MM.xlsx`. Publication stages a
complete workbook under the WO-12 operation root, validates it, atomically
replaces the monthly file, performs byte-for-byte readback and SHA-256
verification, retains a content-bound receipt, then clears staging. Failed
operations retain a failure record and cannot authorize `OPEN MONTHLY EXCEL`.

The ordered sheets are Opportunities, Tracks, Events, Analysis, Data_Quality
and Metadata. Real Excel tables and bounded formulas are permitted. Macros,
external links, hidden executable content, raw market payloads and credentials
are prohibited.

Opportunities retains the complete monthly denominator, including candidates
that never reach WO-09, lack a Trade Plan, receive NONE or DO_NOTHING, never
enter, or finish with ambiguous or unavailable evidence. It projects retained
WO-09 I1-I5 state and first 3/5, 4/5 and 5/5 timestamps; compact Review/WO-07F
lineage; WO-10 geometry, Future market and advisory Risk facts; Sponsor
decisions; and WO-11 summaries. It does not recalculate those authorities.
Missing source facts remain blank and receive explicit Data_Quality rows.

Tracks keeps PAPER Position and Paper Observation in separate one-lot rows.
Entry, exit, points, model R, gross result, holding time, MFE/MAE, eligible
sample count and monitoring coverage come only from retained WO-11 records.
Analysis uses portable audited formulas with visible numerators, denominators
and inclusion rules. PAPER expectancy and monetary results remain separate
from counterfactual Observation results. Events compacts stage changes and
significant WO-11 lifecycle events without copying raw ticks.

The Opportunities page contains `RESEARCH / ANALYSIS DETAILS`. The research
page exposes `UPDATE RESEARCH` and, after receipt verification, `OPEN MONTHLY
EXCEL`. No action is scheduled automatically. Startup, restoration and GET are
read-only. Google Drive integration and configuration are `NOT_COMMISSIONED`.

If the verified monthly XLSX is missing or corrupt, the next explicit UPDATE
RESEARCH rebuilds the same canonical filename from upstream evidence and the
compact WO-12 ledger. When the source boundary is unchanged, recovery
reproduces the exact receipted bytes and retains the existing receipt,
projection and checksum without creating another daily package. A verified
unchanged workbook returns `ALREADY_UP_TO_DATE` without rewriting bytes.
