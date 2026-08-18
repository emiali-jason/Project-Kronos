# KRONOS Swing V1 Main Slice 4D — Alert Publication Provenance

## Authority and lineage

- Contract: `KRONOS-SWING-V1-PINE-EVIDENCE-V1`
- Contract version: `1.1`
- Role: `CANDIDATE / SHADOW_ONLY`
- MCX parent: `59f35175ea0c666fbadef00e6861f42e3c75b858a66891e3908657fd4bb0245d`
- NSE parent: `f7a5098b6c406303686a110849ba93c2a505ffa3e9bd2d6ba77b038aa1639a43`
- MCX 4D candidate SHA-256: `6bf7b7bd58a4bc9c839737a6ec0c258391b3a7c2a087c5cd333c5d8513eda73f`
- NSE 4D candidate SHA-256: `42f527dbd5c20b8c6bd0bdcf94b8635dbc76bd3fe85c76c83916aa8302542136`
- Production authority: unchanged
- Receiver, authentication and persistence: not implemented

Each 4D candidate has its Sponsor-validated 4B/4C source as an exact byte
prefix. The appended code performs exposure, serialization and completed-bar
publication only. It does not alter an earlier declaration or assignment.

## Deterministic representation

Pine emits the frozen v1.1 envelope with lexicographically ordered object
fields, the 14 evidence records in frozen enum order and deterministic compact
JSON. Strings escape backslash, quote, newline, carriage return and tab before
serialization. Unavailable values are `null` with an empty values array; NSE
NOW is explicit `NOT_APPLICABLE / NOT_IN_NSE_V1`.

The semantic representation differs from Python canonical serialization in
one constrained field: Pine has no SHA-256 primitive, so it emits
`"event_id": null`. It includes all frozen event-identity material and complete
evidence, allowing the later authorized KRONOS receiver to derive and verify
the event ID with the frozen 4A formula. HTTP arrival time is absent.

Pine cannot embed the SHA-256 of its own final source without changing that
source and invalidating the hash. The final validated 4D candidate SHA is
therefore a required non-secret script input. Publication remains fail-closed
until its value has exactly 64 characters. Sponsor must paste the reported
candidate SHA without editing the script.

## Boundary and frequency

The payload builder can represent `COMPLETED`, `DEVELOPING` and `UNKNOWN`.
Mandatory alerts publish only on realtime confirmed bars using
`alert.freq_once_per_bar_close`. A persistent last-published bar-close guard
also prevents repeat publication. Developing and unknown states are retained
as explicit non-published diagnostic states.

## Payload budget qualification

The script measures every runtime payload and refuses publication above the
16,384-character internal limit. Tests measure representative canonical MCX
and NSE envelopes and escaping-heavy qualified worst cases. No mandatory field
is dropped to meet the limit.

- MCX representative: `8,544` bytes; escaping-heavy qualified worst case:
  `11,679` bytes.
- NSE representative: `8,644` bytes; escaping-heavy qualified worst case:
  `11,736` bytes.

## Product isolation

MCX serializes `mcx` and emits `nse: null`. NSE serializes `nse` and emits
`mcx: null`. Tests inspect only the appended publication contract, not dormant
cross-product material inherited unchanged from the frozen shared engines.
