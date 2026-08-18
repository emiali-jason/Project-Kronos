# Historical Swing Shadow V0

Status: **NON-AUTHORITATIVE HISTORICAL VALIDATION ARCHIVE**

This package preserves the retired `SWING-V1-SHADOW-MTF-DISCOVERY-V0`
experiment and its validation material.

- **NON-AUTHORITATIVE**
- **NO TRADING AUTHORITY**
- **NO READINESS AUTHORITY**
- **NO EXECUTION AUTHORITY**
- **NOT LOADED BY PRODUCTION RUNTIME**
- **SUPERSEDED BY KRONOS NATIVE DISCOVERY**
- **RETAINED ONLY FOR COMPARISON, REGRESSION RESEARCH, AUDIT AND PROVENANCE**

The archived implementation must not be placed on the production Python import
path or reconnected to Swing orchestration. The historical Browser Shadow test
is a **non-executable historical specification**: it references the retired
`render_shadow_validation` surface and is intentionally excluded from active
pytest collection.

`patches/layer1-shadow-wrapper.patch` records the retired Shadow-only wrapper
that temporarily exposed the existing Daily Layer-1 predicate. Production
`src/kronos/swing/v1/layer1.py` remains at its committed implementation without
that wrapper.
