# TE-03A governed MCX target authority candidate

Status: Sponsor-authorized bounded engineering; exact candidate qualification
and CA review evidence are retained under `output/theta-te03a-closure/`.
No source publication, commit, runtime deployment or production acceptance.

Authoritative develop: `37c9dc94ccbbfd35b78c3dfa7c0369a7f41b0df3`, verified
against the clean main checkout and GitHub branch on 12 October 2026.
The retained Theta tree contained an earlier 40-test target candidate and
MCX source PDFs. This continuation preserves those sources and the prior
publication bytes, and records the final scope in a SHA-256 manifest.

The [authority interface](../architecture/interfaces/KRONOS-MCX-OPTION-TARGET-AUTHORITY-V1.md)
specifies source coverage, ownership, exact option endpoints, compact V3
binding, fail-closed conditions, and review admission. The authority extends
only the three supported December families, separates shared publication
composition from Theta selection, revalidates sources on admission, and binds
review to both domain publications and the current composition hash.

Qualification includes target mappings for all five families; before/exact/
after endpoint behavior; Silver Mini's same-future case; Copper's option/future
cutoff separation; source corruption before/after loading; supersession;
review binding; malformed and absent authority; coverage exhaustion; V3
contract compatibility; TE-02 commissioning with explicitly synthetic method
fixtures; and immutable predecessor Questions/PDFs.

Affected regression scope includes Instrument, Market/calendar, retained Theta,
Swing MCX/futures and Intraday MCX/futures. The protected repository test
launcher denies production stores, credentials and external network calls.
The final JUnit file reports the actual count; no test result grants runtime
or source-publication authority.

CA review must record separate Instrument and Market/calendar dispositions
against the final manifest. No separate current domain-owner task is
established. Review absence is not replaced with an invented approval.

Methodology authority is **NOT_ESTABLISHED**. Target qualification cannot
manufacture it. No genuine Question is commissioned in this slice. The V3
contract source remains byte-identical to TE-04A; the adapter fits its existing
fields. The earlier TE-01/01R/02 and TE-06A implementations are preserved.

Known bounds: GOLDM/SILVERM supported pairs end at their October option
endpoints, while the other three families support November/December pairs.
New sources/calendar coverage require reviewed successor publications.
Offline currentness cannot assert that no new MCX amendment exists.

Next: TE-04B — NOT STARTED.
