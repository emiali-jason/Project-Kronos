# ADR-0036 — Ordered mixed Review batch transport

**Status:** Sponsor-approved decision; engineering candidate, not published.
**Authority:** WO-07E Batch Review Compilation Correction, 2026-09-10.
**Scope:** Explicit Sponsor batch Question generation and Answer import only.

CREATE ALL REVIEW PDF compiles the exact current Review pointer population in
its retained order into one PDF and declares one batch Answer filename. Every
candidate must have a valid current chart before export. No partial population
or per-candidate Sponsor export is permitted during this batch action.

A separate versioned batch envelope binds the Review pointer, run, ordered cycles,
chart revisions, packs and candidate identities. Candidate Answer payloads retain
their existing NSE or paired MCX schema. The batch carries a per-member global
status; NSE must agree with its payload and MCX uses the existing question-level
status composition without adding keys to the paired payload.

Envelope, population, order and all member bindings are checked before any Answer
persistence. Bound candidates then pass their existing schema, identity, chart
correspondence and temporal gates independently. Successful members are retained;
rejected members remain rejected. Results retain Review order and cannot describe
a partly rejected batch as wholly accepted. Identical successful replay reports
ALREADY_IMPORTED; conflicting answers remain rejected. Currentness is rechecked
at each persistence boundary. No fallback to separate candidate files occurs when
a current batch commission exists.

Individual generation/import and historical transport formats remain available.
98/98 identity capability, NATGAS HELD, ADR-0034 MCX family/contract separation,
supporting-only references, and ADR-0035 temporal composition are unchanged.
No analytical, trading, runtime, Provider or production-operation authority is
granted by this engineering change. No production evidence is rewritten.
