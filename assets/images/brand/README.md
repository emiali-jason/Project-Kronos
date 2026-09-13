# KRONOS brand assets

`kronos-logo-master.png` is the Sponsor-approved full-resolution master artwork.
It is retained byte-for-byte and is not loaded by the Browser shell.

`kronos-brand-mark.png` is the optimized 512 px shared-shell asset derived
mechanically from the complete master. It retains the approved clock/K mark,
KRONOS wordmark, and `by Imran` signature without a runtime dependency on the
large master.

`kronos-favicon.png` and the macOS template icon are compact mark derivatives
from crop `(270, 90, 985, 805)`. Derived assets contain no EXIF or other
ancillary metadata. They do not change the bundle identifier, signing identity,
canonical launcher guard, or runtime authority.

## UI-BRAND-01A sidebar derivative

Status: Approved Sponsor presentation refinement; engineering candidate.

`kronos-sidebar-mark.png` is a 192 × 192 RGB PNG, mechanically derived from
master crop `(307, 125, 947, 765)` using Lanczos resampling and PNG optimization.
The square crop preserves the approved K/clock-orbit geometry and metallic/blue
artwork. It is a separate asset; the master, existing full-artwork derivative,
favicon and app icon remain unchanged.

The shared shell renders the derivative at 72 × 72 CSS pixels (the orbit itself
is approximately 65 pixels wide), above a 20-pixel KRONOS wordmark and subordinate
11-pixel `by Imran` signature. Explicit image dimensions reserve layout space.
All products consume the same markup and fixed local PNG route. There is no
runtime image processing, new polling, remote asset or navigation change.

Included in the combined WO-15/WO-16 candidate, without a separate release.

At 761–1200 pixels, shared headings grow to fit and the existing Intraday
workflow and action rows stack, preventing clipping/crowding while preserving
all controls, route identities and sidebar width.
