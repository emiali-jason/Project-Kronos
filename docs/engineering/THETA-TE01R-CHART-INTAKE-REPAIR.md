# Theta TE-01R chart intake availability repair

**Owner:** EA-Theta Earners. **Authority:** Sponsor's bounded TE-01R defect
repair order. **Status:** Qualified isolated sandbox repair, 12 October 2026.
No publication, production deployment or runtime acceptance is granted.

The Sponsor sandbox now admits the existing governed Theta chart-intake route
while retaining its other mutation prohibitions. Six real Chrome clipboard
replacements, native PNG/JPEG file selection, fail-closed checks and restart
recovery qualify this composition. Application and shared Browser source remain
unchanged from the retained TE-06A checkpoint.

## Root cause

PID 9279 on 8948 was running the TE-06A **visual-only** launcher. Its handler
overrode every POST/PUT/PATCH/DELETE with a text/plain 405 response. GET routes
still exposed retained charts, so GLOBAL_MACRO correctly appeared ready while
its mutation capability was absent. The unchanged chart script expected JSON
from the upload route; parsing the text denial entered its
`CHART_INTAKE_UNAVAILABLE` catch path.

The failure was reproduced with a real PNG clipboard and Cmd+V in Chrome and a
bounded invalid HTTP request. Both reached the blanket preview denial. Theta
route registration remained intact. Neither TE-02 binding rules nor TE-06A
theme code removed the chart route. The regression was the running sandbox's
capability mismatch with Sponsor chart-intake use, not a persistence defect.

The old launcher also seeded its initial fixture on every start. Reusing that
startup after permitting replacement could overwrite a selected replacement
with the fixture. The repair therefore restores the retained disposable store
without reseeding, generating Questions or importing Answers.

## Bounded repair

`output/theta-te01r-chart-repair/sandbox_launcher.py` is a qualification helper,
not a production launcher, provider surface or application registration. It
permits only exact `POST /theta-earners/chart`, delegating to the unchanged shared
handler. Shared exact loopback Host/Origin, shutdown/maintenance admission,
request-size bounds and Theta role/cycle/revision/image validation remain active.
All other POSTs and all PUT/PATCH/DELETE requests remain 405. Non-Theta reads
remain 403 in this sandbox.

The exact-origin requirement is `http://127.0.0.1:8948`, including the exact Host
authority. The existing GET-only localhost redirect is retained. There is no
direct dispatch around shared admission, broad mutation switch or removal of
the unavailable-state message.

The child retains kernel denial of production evidence, credentials and all
network except 8948 loopback. It uses an isolated home, explicit disposable
Theta paths, scrubbed environment, a forbidden Provider factory and disabled
service pulses. Provider calls remained zero. No broker or order endpoint was
used. Production 8947 was not queried, stopped, restarted or written; its
listener remained PID 95115.

## Real Browser qualification

All six roles passed **Replace Chart → focused card → Cmd+V** using labelled
synthetic composites: GOLDM, SILVERM, COPPER, CRUDEOIL, NATURALGAS and GLOBAL_MACRO.
Each selected a new revision/SHA, bound its predecessor and acceptance receipt,
and left the other five chart roles unchanged. Old chart, revision, Question,
Answer, receipt and transport bytes remained immutable.

The real native macOS picker accepted a GOLDM JPEG and a SILVERM PNG through the
visible Choose File label. Their retained preview hashes match the exact source
files. The JPEG selected a new revision. The PNG replayed the already selected
exact bytes and correctly reused its revision and receipt rather than inventing
a replacement. Clipboard and file input use the existing common `receive` path; no
alternate collector or persistence mechanism was added. Invalid clipboard text
produced `NO_IMAGE_IN_CLIPBOARD` without any store mutation.

The extension's automated file-setting path timed out. Native picker
qualification completed after Sponsor unlocked the Mac; no extension permission
was changed by Codex. A fresh preview tab replaced the stalled automation tab.
The clipboard tests replaced clipboard contents with synthetic data without
reading the previous clipboard. The final clipboard holds the synthetic Macro
PNG. Actual Windows/Linux Ctrl+V was not exercised on this Mac.

Two bounded 8948 restart checks restored the same selections: first after the
six clipboard replacements, then after the native file replacements. Neither
restart rewrote retained evidence or reseeded fixtures.

## Binding and safety qualification

Commodity replacement made its prospective Question/Answer noncurrent without
changing other commodity chart roles or their current bindings. Shared Macro
replacement invalidates all prospective Questions bound to that Macro; separate
synthetic HTTP cases prove this even when all five Questions are still current.
Historical V1 behavior and artifacts are unchanged. The combined transport now
shows `QUESTION INPUTS CHANGED — RECREATE PACK`, not a current pack against
replaced charts. Question/Answer POSTs remain disabled in this sandbox.

Live denial checks returned 403 for foreign/missing Origin and foreign Host,
409 for invalid image bytes, 405 for non-chart mutations and route variants,
and 403 for non-Theta reads. Store inventories remained unchanged by these
checks. Tests also prove stale revision rejection, body bounds, delegated
admission refusal, exact original previews, selection history and no mtime or
directory-order fallback.

## Tests and retained evidence

The protected runner completed **242 passed, zero failures, errors or skips**:
the retained 208 Theta/Browser cases plus 34 new sandbox qualification cases.
Console duration was 79.33 seconds; JUnit duration was 79.260 seconds.

Command:

```text
tools/kronos_test.py tests/unit/theta tests/unit/browser/test_product_route_isolation.py -q --junitxml=output/theta-te01r-chart-repair/functional-regression.xml
```

The initial run exposed a test-fixture omission: restored unselected roles lacked
the synthetic authority adapter. The corrected fixture restores the same
composition and passes; no application change was needed. An initial launcher
attempt under `/private/tmp` was rejected by the existing Swing evidence-root
guard before a listener was started. The retained macOS temporary-root convention
resolved that restriction without weakening the guard.

Evidence is in `output/theta-te01r-chart-repair`: pre/post Browser screenshots,
12 Browser checkpoints, read-only live store/preview checkpoints, exact synthetic
inputs, JUnit, qualification summary and SHA-256 source/artifact manifest.
The writing skill keeps this engineering record scoped to verified facts and
the Sponsor's existing repository documentation format.

## Changed files and retained boundaries

New controlled files:

- `tests/unit/theta/test_sandbox_chart_admission.py`.
- `docs/engineering/THETA-TE01R-CHART-INTAKE-REPAIR.md`.

New qualification helpers and generated artifacts are confined to
`output/theta-te01r-chart-repair` and the explicit disposable temporary root.
The existing TE-06A helper and historical closure artifacts are not rewritten.
All prior source hashes are checked against the TE-06A manifest. No source under
`src/`, repository index, commit, schema or production configuration changed.
Swing and Intraday impact is none; their sandbox routes remain inaccessible.

The final sandbox is
`http://127.0.0.1:8948/theta-earners/new-analysis`, PID **12264**, kept running
for Sponsor inspection. Its evidence and clock remain visibly synthetic; the
clock is frozen at `2026-10-11T13:00:00+00:00`, not a genuine upload chronology or
forecast information cutoff. Genuine target/methodology commissioning and
Question/Answer mutation authority are outside TE-01R. No further slice began.
