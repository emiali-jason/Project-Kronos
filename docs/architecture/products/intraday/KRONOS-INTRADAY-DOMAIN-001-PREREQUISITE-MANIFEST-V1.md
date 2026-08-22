# Intraday DOMAIN-001 Prerequisite Manifest V1

**Status:** Platform work-order proposal; not implemented by WO-03A
**Owner:** DOMAIN-001
**Consumer:** Intraday

WO-03A found one canonical-ready member (RELIANCE) and 97 canonical gaps. The
Sponsor memberships remain governed in the Intraday publication, but WO-03
must fail closed for each unavailable member.

## Exact prerequisite scope

DOMAIN-001 requires a separately reviewed, effective-dated canonical catalogue
publication for these 97 Sponsor labels:

ADANIENT, ADANIGREEN, ADANIPORTS, ALKEM, APOLLOHOSP, ASIANPAINT, AXISBANK,
BAJAJFINSV, BAJAJ_AUTO, BAJFINANCE, BDL, BEL, BHARATFORG, BHARTIARTL, BHEL,
BPCL, BSE, CANBK, CDSL, CIPLA, COALINDIA, COFORGE, CONCOR, CUMMINSIND,
DIVISLAB, DIXON, DRREDDY, EICHERMOT, ETERNAL, FEDERALBNK, HAL, HCLTECH,
HDFCAMC, HDFCBANK, HDFCLIFE, HEROMOTOCO, HINDALCO, HINDPETRO, HINDUNILVR,
ICICIBANK, IDEA, INDHOTEL, INDIANB, INDIGO, INFY, IOC, ITC, JIOFIN, JUBLFOOD,
KAYNES, KOTAKBANK, LICI, LT, LUPIN, M&M, MARUTI, MAXHEALTH, MAZDOCK, MCX,
MOTHERSON, MUTHOOTFIN, NAUKRI, NTPC, PAYTM, PERSISTENT, PNB, POLICYBZR,
POWERGRID, POWERINDIA, RBLBANK, RECLTD, RVNL, SAIL, SBICARD, SBIN,
SHRIRAMFIN, SRF, SUNPHARMA, TATAPOWER, TATASTEEL, TCS, TECHM, TITAN, TMPV,
TRENT, UPL, VBL, VEDL, WIPRO, YESBANK, NIFTY, BANKNIFTY, GOLDM, SILVERM,
COPPER, NATGAS, CRUDE.

For every record DOMAIN-001 must govern the exact canonical identity, exchange,
segment, instrument type, tick size, lot size, price precision, validity,
source, provenance, integrity, and any Provider binding directive. Provider
instrument-master presence is evidence input only and cannot create canonical
meaning. Persistent MCX analytical subjects must remain distinct from
expiry-listed contracts and from later active-contract selection.

## Proposed bounded Platform manifest

- Add a new version under
  `data/instruments/KRONOS-CANONICAL-INSTRUMENT-CATALOGUE-V1/`.
- Add focused catalogue coverage, ambiguity, staleness, and binding-directive
  tests under `tests/unit/instrument/`.
- Modify DOMAIN-001 code only if its existing publication contract cannot
  represent persistent MCX subjects or multiple canonical market families.
- Do not modify the Intraday 1.0.0 universe publication in that work order.

Authoritative source facts are not yet repository-complete for the 97 members;
therefore WO-03A does not manufacture this publication mechanically.
