"""Deterministic known-truth fixtures for future 4E panel transcription tests."""

from __future__ import annotations

from kronos.swing.v1.visible_pine_evidence import (
    VISIBLE_PINE_PANEL_CONTRACT_ID,
    VISIBLE_PINE_PANEL_DOMAIN_ROWS,
    VISIBLE_PINE_PANEL_VERSION,
    VisiblePineBoundaryState,
    VisiblePineKnownTruthFixture,
    VisiblePinePanelProduct,
    VisiblePinePanelRow,
)


def _rows(product: VisiblePinePanelProduct) -> tuple[VisiblePinePanelRow, ...]:
    mcx = product is VisiblePinePanelProduct.MCX
    prefix = "MCX" if mcx else "NSE"
    instrument = "MCX:GOLD1!" if mcx else "NSE:RELIANCE"
    product_rows = (
        (
            VisiblePinePanelRow(
                "MCX_CONTEXT_1",
                "ANALYSIS ID=MCX Metals Swing | REF MARKET=COMEX | REF TF=D",
            ),
            VisiblePinePanelRow(
                "MCX_CONTEXT_2",
                "REF STATE=AVAILABLE | REF ALIGN=READY | READINESS=QUALIFIED",
            ),
            VisiblePinePanelRow(
                "MCX_CONTEXT_3",
                "NOW=BUY NOW | PRODUCT=MCX",
            ),
        )
        if mcx
        else (
            VisiblePinePanelRow(
                "NSE_CONTEXT_1",
                "ANALYSIS ID=NSE:RELIANCE | CHART SYMBOL=NSE:RELIANCE | "
                "SECTOR=NSE:CNXENERGY | PARENT=NSE:NIFTY",
            ),
            VisiblePinePanelRow(
                "NSE_CONTEXT_2",
                "SECTOR STATE=1 | MARKET STATE=MARKET STRONG | REF ALIGN=1 | "
                "REF COMPLETE=VALID",
            ),
            VisiblePinePanelRow(
                "NSE_CONTEXT_3",
                "READINESS=QUALIFIED | NOW=NOT_APPLICABLE | PRODUCT=NSE",
            ),
        )
    )
    return (
        VisiblePinePanelRow("SECTION A", "IDENTITY + MARKET EVIDENCE"),
        VisiblePinePanelRow("PANEL_SCHEMA", VISIBLE_PINE_PANEL_CONTRACT_ID),
        VisiblePinePanelRow("PANEL_VERSION", VISIBLE_PINE_PANEL_VERSION),
        VisiblePinePanelRow("PRODUCT", product.value),
        VisiblePinePanelRow("PINE_IDENTITY", f"KRONOS-{prefix}-VISIBLE-CANDIDATE"),
        VisiblePinePanelRow("PINE_VERSION", "0.6.0+VISIBLE-1.0"),
        VisiblePinePanelRow("PINE_BUILD", f"0005-4D-V-{prefix}"),
        VisiblePinePanelRow("PUBLISHER_ROLE", "CANDIDATE"),
        VisiblePinePanelRow("CANONICAL_INSTR", instrument),
        VisiblePinePanelRow("TIMEFRAME", "60"),
        VisiblePinePanelRow("OBS_BOUNDARY", f"{instrument}|60|1000|2000"),
        VisiblePinePanelRow("BOUNDARY_STATE", "COMPLETED"),
        VisiblePinePanelRow(
            "STRUCTURE", "BULLISH | HH=YES | HL=YES | LH=NO | LL=NO"
        ),
        VisiblePinePanelRow("VISIBLE_SWINGS", "SWING HIGH=100 | SWING LOW=90"),
        VisiblePinePanelRow("STRUCTURE_BREAK", "BOS=BULLISH | CHOCH=NONE"),
        VisiblePinePanelRow(
            "RANGE", "NOT_RANGE | RANGE HIGH=UNAVAILABLE | RANGE LOW=UNAVAILABLE"
        ),
        VisiblePinePanelRow(
            "BREAK", "BREAKOUT | BREAK DIR=BULLISH | BREAK ACCEPT=ACCEPTED"
        ),
        VisiblePinePanelRow(
            "SMA20",
            "VALUE=98 | SLOPE=RISING | PRICE RELATION=ABOVE | "
            "INTERACTION=UNAVAILABLE | REL=BULLISH",
        ),
        VisiblePinePanelRow(
            "SMA50",
            "VALUE=95 | SLOPE=RISING | PRICE RELATION=ABOVE | "
            "INTERACTION=UNAVAILABLE | REL=BULLISH",
        ),
        VisiblePinePanelRow(
            "SMA200",
            "VALUE=85 | SLOPE=UNAVAILABLE | PRICE RELATION=ABOVE | "
            "INTERACTION=UNAVAILABLE | REL=BULLISH",
        ),
        VisiblePinePanelRow(
            "CANDLE",
            "ACCEPT=ACCEPTED | BODY=.600 | UWICK=.100 | LWICK=.100 | "
            "CLOSE LOC=.800 | NORM RANGE=1.200 | CLOSE PRESS=STRONG BULLISH",
        ),
        VisiblePinePanelRow(
            "VOLUME",
            "VOLUME=1000 | VOL REF=900 | VOL STATE=PARTICIPATING | "
            "PARTICIPATION=YES | VOL MODE=NO COMPRESSION",
        ),
        VisiblePinePanelRow(
            "REFERENCE_LEVELS",
            "CP=96 | TC=97 | BC=95 | REF SUP=UNAVAILABLE | "
            "REF RES=UNAVAILABLE | REF HIGH=101 | REF LOW=91 | REF REL=ABOVE CPR",
        ),
        VisiblePinePanelRow(
            "BARRIERS",
            "BARRIER=NO | BARRIER TYPE=CPR | BARRIER PX=UNAVAILABLE | "
            "BARRIER REL=ABOVE CPR | BARRIER STATE=ACCEPTED",
        ),
        VisiblePinePanelRow("SECTION B", "PINE STATE + PRODUCT CONTEXT"),
        VisiblePinePanelRow("TREND", "CONFIRMED BULLISH"),
        VisiblePinePanelRow("QUALITY", "HEALTHY"),
        VisiblePinePanelRow("ACCEPTANCE", "ACCEPTED"),
        VisiblePinePanelRow("MOMENTUM", "STRONG"),
        VisiblePinePanelRow("OPPORTUNITY", "FAVORABLE"),
        VisiblePinePanelRow("CONFIDENCE", "80 | HIGH"),
        VisiblePinePanelRow("DECISION", "WATCH LONG"),
        VisiblePinePanelRow("NEED", "NONE"),
        VisiblePinePanelRow("STATUS", "VALID"),
        *product_rows,
    )


MCX_VISIBLE_PANEL_KNOWN_TRUTH = VisiblePineKnownTruthFixture(
    fixture_id="SWING-V1-VISIBLE-PANEL-MCX-KNOWN-TRUTH-V1",
    product=VisiblePinePanelProduct.MCX,
    canonical_instrument="MCX:GOLD1!",
    timeframe="60",
    boundary_state=VisiblePineBoundaryState.COMPLETED,
    publisher_role="CANDIDATE",
    rows=_rows(VisiblePinePanelProduct.MCX),
    pine_owned_domains=VISIBLE_PINE_PANEL_DOMAIN_ROWS,
    product_extension=("MCX_CONTEXT_1", "MCX_CONTEXT_2", "MCX_CONTEXT_3"),
)

NSE_VISIBLE_PANEL_KNOWN_TRUTH = VisiblePineKnownTruthFixture(
    fixture_id="SWING-V1-VISIBLE-PANEL-NSE-KNOWN-TRUTH-V1",
    product=VisiblePinePanelProduct.NSE,
    canonical_instrument="NSE:RELIANCE",
    timeframe="60",
    boundary_state=VisiblePineBoundaryState.COMPLETED,
    publisher_role="CANDIDATE",
    rows=_rows(VisiblePinePanelProduct.NSE),
    pine_owned_domains=VISIBLE_PINE_PANEL_DOMAIN_ROWS,
    product_extension=("NSE_CONTEXT_1", "NSE_CONTEXT_2", "NSE_CONTEXT_3"),
)
