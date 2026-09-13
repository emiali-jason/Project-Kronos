# ADR-0051 — Swing V3 immutable rendered-artifact recovery

**Status:** Sponsor/EA authorized bounded EVIDENCE-RECOVERY-01/01A engineering; candidate subject to qualification and Sponsor review. Production supersession, publication and runtime operations are not authorized by 01A.

## Authority and scope

Sponsor orders 778db8dc and fed70ac3 authorize exact source reconciliation, a layout-only renderer correction, immutable successor artifacts and isolated persistence/restoration qualification. The selected Review is KRONOS-V3-REVIEW-BA8681C0DACC46F98E9E51FEFEA037D3. Its canonical Native/fact/chart sources agree; the original PDF has malformed ASCII85/xref data and a stale embedded Review identity. Its matching historical hash does not prove validity. The first unselected replacement is structurally valid but clips contract text. Both files remain immutable evidence.

This adds explicit artifact lineage to the existing V3 PDF transport. It does not supersede question set 3.1, analytical Review, Answer contracts or RUNTIME-01 health gates. No recovery occurs automatically and no Browser/API production recovery action is exposed.

## Renderer-only successor

SWING-V3-ANSWER-CONTRACT-RENDERER / 1.1.0 uses A4 with 54-point margins on all sides and the document frame's 6-point inner padding: usable width 475.27559055118115 points. Courier 7.5-point text uses 10-point line height; BodyText uses 9/12 points with 6-point paragraph spacing. Contract blocks have 8-point trailing spacing. A block splits only between measured lines; less than one 10-point line of remaining height moves the next line to the next page. Existing paragraphs paginate normally.

The binary-search width measurement uses actual font metrics. It prefers a space boundary while retaining that exact space; unbroken identities split at measured character boundaries. Only presentation newlines are inserted. No character, value, label, ordering, font compression, truncation, ellipsis or invented continuation marker is introduced. Larger page counts are lawful. The transport remains 3.0 and question set/Answer schema remain 3.1; renderer identity is separate.

## Immutable recovery contract

SWING_V3_REVIEW_ARTIFACT_RECOVERY_V1 / 1.0.0 is an explicit administrative artifact transaction. It binds the exact canonical pack digest and Review identity; original path/hash; successor path/hash; original malformed structure and stale embedded identity; classification PDF_RENDERING_PLUS_STALE_EMBEDDED_IDENTITY; renderer identity/version; retained generation policies; retained source paths/hashes; Sponsor authorization reference; visual-QA report hash; timezone-aware creation time; and canonical JSON SHA-256 checksum.

Disposition is HISTORICAL_INVALID_RENDERED_ARTIFACT for the original and CURRENT_VALID_RENDERED_ARTIFACT for the successor. The latter is a fixture disposition until separately authorized production application. No new analytical Review is created.

The renderer accepts only the exact candidate ordering/population, four timeframe bindings, Native run/assessment, chart hashes, machine-fact hashes, request time and governed question version from the original pack. Generation is no-clobber. Selection requires exact regenerated PDF bytes, independent strict stream/parser and Review-binding checks, prior source/visual qualification, and an unchanged original hash. It refuses a currently valid original or altered analytical projection.

The original review-packs JSON is never replaced. The selected record is a projection changing only Question artifact filename/path/hash in the pack and its five candidate bindings. Expected Answer filename, Review identity, all analytical/time/version/scope fields and Answer-import records remain unchanged.

The original selection is retained immutably under selection-history by its canonical digest. The recovery record is retained under artifact-recoveries by checksum. Only then is current-review-pack.json atomically replaced with the original schema/Review ID plus artifact_recovery_sha256. Interrupted publication leaves only unselected lineage evidence. Repeating the exact transaction is idempotent; changed replay inputs fail closed. Selection remains the final commit point under the existing cycle lock.

## Restoration and preservation

Selected recovery resolution validates checksum, canonical pack binding, predecessor identity/hash, retained source hashes, renderer identity and successor structure/hash/Review binding before returning the artifact projection. Exact replay uses that projection without silently reselecting an older Review. Missing/tampered lineage or source remains unavailable; no fallback hides the original failure.

The three retained incomplete Answer imports stay ANSWER_PACK_INCOMPLETE and unconsumed. Restoring their selected Review does not construct responses, promote candidates or create monitoring owners. Existing RUNTIME-01 automatic startup can pass only after unchanged WO-06H restoration, valid Swing retained state, no unexpected Provider capability and no unexpected transport. The production PID stays FAILED_ACTIVE throughout engineering.

Swing timeframes, Native states, KR-370, Step-31, Risk, PAPER/LIVE/IGNORE, timing, monitoring, Notifications, Journal, Portfolio and Reports are unchanged. Intraday RUNTIME-01/WO-06H/09/10/11/12 remain unchanged. No production pointer/PDF/recovery record, Provider connection, maintenance exit or restart is authorized by this candidate.

## Qualification

Required: measured short/long/multiple values and unbroken identities; bottom-edge/page-break tests; exact repeated-render bytes; full structural/visual QA; retained five-candidate/20-chart/20-fact/200-question equivalence; exact contract values; isolated immutable pointer transaction; original and failed PDF preservation; three incomplete imports; idempotent restoration and shared startup health; tampering/failed-commit negatives; affected/full regression, compile, JavaScript, complete diff, documents and sensitive-material checks.

Qualification evidence and PDFs belong outside canonical production stores. Candidate hashes and results are frozen in the task qualification report. Production recovery requires a separate Sponsor/EA decision after engineering review.
