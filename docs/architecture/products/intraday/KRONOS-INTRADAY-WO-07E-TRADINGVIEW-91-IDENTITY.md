# WO-07E — TradingView 91-equity visual identity completion

Status: Sponsor-authorized engineering candidate under ADR-0018; publication,
deployment and production operations require separate authorization.

## Source and exact canonical reconciliation

The Sponsor declares `Kronos Stocks_2026-09-10_61339.csv` was downloaded directly
from TradingView on 10 September 2026. Source authority is
`SPONSOR_PROVIDED_TRADINGVIEW_EXPORT`, not a verified TradingView API/feed.
The unchanged UTF-8, comma-delimited, quoted CSV is retained at
`data/instruments/KRONOS-GOVERNED-VISUAL-IDENTITY-RELATIONSHIP-PUBLICATION-V1/sources/tradingview-nse-equities-2026-09-10.csv`.
Its SHA-256 is
`1c1f9d60d5dcc471ad55593253c0d52ea63b3c4feddecee02a35d3982b80f29d`.

There are 91 data rows and 17 columns. The companion `1.6.0-coverage.json` retains
the exact column names, original source path, source hash, exact Symbol and
Description, row number/hash, governed canonical binding, relationship identity,
publication identity/integrity and effective interval for every equity.
Venue and instrument type are not separate CSV fields: they are not claimed
as independently observed CSV facts. The Sponsor declares the NSE-equity scope;
canonical catalogue 1.2.0 and native universe 1.0.0 independently establish each
of the 91 exact governed members. Price, ratings and other exported fields have
no analytical/admission/Assessment authority in this work.

The exact `NSE:` venue qualifier is used to compare the export's bare Symbol to
the explicitly governed NSE symbol binding. The bare Symbol is retained unchanged.
No punctuation, case or company-name normalization is performed. The catalogue's
membership source identity ties each native-universe member to its canonical
object; a canonical ID is never manufactured from Description.
`BAJAJ_AUTO` remains the existing governed binding to `NSE-EQ-BAJAJ-AUTO`;
`RELIANCE` remains canonical `RELIANCE`; `M&M` remains canonical `NSE-EQ-M&M`.
The approved 91-pair binding set is digest-pinned alongside the source hash.

Reconciliation is 91 matched, zero missing, extra, duplicate, ambiguous, blank
or mismatched identities. The qualifier also reports missing/extra rows
explicitly and excludes them from matched records. Duplicate Symbols,
ambiguous Descriptions, malformed rows, unapproved source and altered source
bytes fail closed. Requalification requires a separately authorized source;
a different checksum cannot be passed to the publication builder to bypass
the Sponsor-approved source pin.

## Immutable successor and effective authority

Explicit successor 1.6.0 retains all 49 records from 1.5.0 exactly, and adds
46 distinct exact labels. It contains 95 relationships covering 91 equities
plus the existing BANKNIFTY relationship. Forty-five CSV labels already have
identical older governed records; those records are reused rather than creating
ambiguous overlapping duplicates. Three other previously covered equities gain
separate, newly evidenced alternate exact labels:

| Canonical subject | Preserved older label | New exact CSV label |
|---|---|---|
| NSE-EQ-DIVISLAB | Divis Laboratories Limited | Divi's Laboratories Limited |
| NSE-EQ-PERSISTENT | Persistent Systems Ltd. | Persistent Systems Limited |
| NSE-EQ-RBLBANK | RBL Bank Ltd | RBL Bank Ltd. |

All export-only labels begin at **2026-09-10T17:18:30.613955+05:30**
(2026-09-10T11:48:30.613955+00:00). The Sponsor explicitly approved this
conservative local source-retention boundary. Exact TradingView export time
is NOT_ESTABLISHED. Neither the filename nor an August record backdates this
source. Earlier records preserve their original lawful intervals and identities.
Every newly added relationship carries exact Symbol/Description, source and row
hashes, source qualification and retained-time provenance. Reused relationships
retain original provenance; the coverage manifest records their additional CSV
corroboration without changing their historical identities.

The stated 17:03 IST Review remains supported for INDIGO, NTPC and VEDL only
among its seven equities. JUBLFOOD, LUPIN, MOTHERSON and YESBANK fail closed at
that boundary and resolve at/after the new effective start. No historical Review,
Answer or failure is rewritten. A later lawful Review boundary is required to
use an export-only relationship; this engineering task does not generate one.

| Canonical identity | Exact Symbol | Exact Description |
|---|---|---|
| NSE-EQ-INDIGO | INDIGO | InterGlobe Aviation Ltd |
| NSE-EQ-JUBLFOOD | JUBLFOOD | Jubilant Foodworks Limited |
| NSE-EQ-LUPIN | LUPIN | Lupin Limited |
| NSE-EQ-MOTHERSON | MOTHERSON | Samvardhana Motherson International Limited |
| NSE-EQ-NTPC | NTPC | NTPC Limited |
| NSE-EQ-VEDL | VEDL | Vedanta Limited |
| NSE-EQ-YESBANK | YESBANK | Yes Bank Limited |
| NSE-EQ-M&M | M&M | Mahindra & Mahindra Ltd. |

## Composition, safety and historical evidence

Current Intraday Review and chart-input composition explicitly select 1.6.0;
there is no directory scan for a latest publication. CSV ingestion is an
engineering publication operation, never a runtime company-name fallback.
The existing exact, source-qualified, effective-dated resolver is unchanged.
Historical revalidation selects the exact retained publication version/integrity;
1.3.0, 1.4.0 and 1.5.0 bytes are unchanged. V1/V2 replay remains compatible.

Unknown aliases, unapproved punctuation/case, wrong-source requests and
pre-effective requests reject. A foreign candidate's legitimate label may resolve
to that other canonical subject, but the unchanged Answer-import expected-subject
gate rejects the mismatch. Publication integrity, duplicate and conflict checks
remain active. No fuzzy, generic display-name, catalogue-name, Kite, internet or
LLM identity-equivalence fallback is introduced.

The CSV does not cover indices. BANKNIFTY's `Nifty Bank Index` is preserved;
NIFTY remains unsupported pending separate exact evidence. The Sponsor's final
closure requirement is still 91 equities + 2 indices + 5 MCX families = 98/98.
This bounded equity candidate does not claim final WO-07E closure or MCX
operational completion. CRUDE, NATGAS, GOLDM, SILVERM and COPPER remain a separate
exact-source follow-up; native-contract and supporting-only reference authority
are unchanged. No CSV-derived MCX relationships are created.

Temporal correspondence, all three temporal result states, the single Question
PDF, Answer Protocol, chart_observation_header, strict V2 validation and Q6/Q9
anchor NOT_ESTABLISHED are unchanged. REV002 negative temporal evidence and all
historical Question/Answer/rejection evidence remain immutable.

## Qualification and operation boundary

Tests cover exact source and canonical membership, every equity's source row and
resolution, before/at/after intervals, the seven equities at 17:03 and after the
new boundary, M&M punctuation, retained alternate labels, separate indices/MCX,
wrong Symbol/Description/candidate/source, duplicates, ambiguity, source and
publication tampering, immutable historical replays and inert runtime composition.
Seven isolated V2 binding fixtures use the successor after its effective boundary;
these are identity tests, not new empirical Chart Analyst/image qualification.

Run dedicated, focused, affected and full repository tests through
`tools/kronos_test.py`, which denies production stores and external network.
Freeze all candidate hashes and retain exact results outside the repository.
No production Review/Question/Answer, Provider, Refresh/Discovery, Chart Analyst,
OpenAI or broker operation, runtime restart, staging, commit or push is authorized.
FB01 and WO-07F remain held. Production inventories must distinguish any concurrent
runtime writes from engineering actions without inventing initiating attribution.
