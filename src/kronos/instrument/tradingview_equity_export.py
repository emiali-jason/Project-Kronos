"""Bounded exact Sponsor TradingView export qualification; no runtime fallback.

ADR-0018: Symbol binds to an already-governed canonical subject. Description
is retained literally, never used to derive canonical identity.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from io import StringIO
import json
from collections import Counter

from kronos.instrument.visual_identity import (
    VisualIdentityRelationshipPublication, VisualIdentitySourceContext,
    VisualIdentityRelationshipStatus, create_visual_identity_publication,
    create_visual_identity_relationship,
)

SPONSOR_TRADINGVIEW_EXPORT = 'SPONSOR_PROVIDED_TRADINGVIEW_EXPORT'
TRADINGVIEW_91_BINDINGS_SHA256 = '4f42ce6e54d0da44b395b18bf56dac222aa1552ec39dce8dffd13c19dadc8f93'
TRADINGVIEW_91_SOURCE_SHA256 = '1c1f9d60d5dcc471ad55593253c0d52ea63b3c4feddecee02a35d3982b80f29d'
TRADINGVIEW_91_RETAINED_AT = datetime.fromisoformat('2026-09-10T11:48:30.613955+00:00')
TRADINGVIEW_91_COLUMNS = (
    'Symbol', 'Description', 'Sector', 'Index', 'Price', 'Price - Currency',
    'Price change %, 1 day', 'Volume, 1 day', 'Relative volume, 1 day',
    'Market capitalization', 'Market capitalization - Currency',
    'Price to earnings ratio', 'Earnings per share diluted, Trailing 12 months',
    'Earnings per share diluted, Trailing 12 months - Currency',
    'Earnings per share diluted growth %, TTM YoY', 'Dividend yield %, Trailing 12 months',
    'Analyst rating',
)


@dataclass(frozen=True)
class QualifiedEquityLabel:
    canonical_identity: str
    symbol: str
    description: str
    row_number: int
    row_sha256: str


@dataclass(frozen=True)
class QualifiedTradingViewExport:
    source_sha256: str
    row_count: int
    matched: tuple[QualifiedEquityLabel, ...]
    missing: tuple[str, ...]
    extra: tuple[str, ...]
    source_authority: str = SPONSOR_TRADINGVIEW_EXPORT


def qualify_tradingview_equity_export(
    payload: bytes, *, symbol_bindings: tuple[tuple[str, str], ...],
    expected_sha256: str = TRADINGVIEW_91_SOURCE_SHA256,
    source_authority: str = SPONSOR_TRADINGVIEW_EXPORT,
) -> QualifiedTradingViewExport:
    """Validate bytes and reconcile exact venue-qualified governed symbols.

    The export does not contain a venue column. The Sponsor-declared NSE export
    scope qualifies its bare Symbols against explicit NSE:<Symbol> bindings;
    no punctuation or symbol spelling is transformed. Missing/extra rows are
    reported, never silently published. Duplicate/ambiguous rows fail closed.
    """
    if source_authority != SPONSOR_TRADINGVIEW_EXPORT:
        raise ValueError('TRADINGVIEW_EXPORT_SOURCE_INVALID')
    if type(payload) is not bytes or sha256(payload).hexdigest() != expected_sha256:
        raise ValueError('TRADINGVIEW_EXPORT_INTEGRITY_INVALID')
    try:
        rows = list(csv.reader(StringIO(payload.decode('utf-8-sig'), newline=''), strict=True))
    except (UnicodeError, csv.Error) as error:
        raise ValueError('TRADINGVIEW_EXPORT_PARSE_INVALID') from error
    if not rows or tuple(rows[0]) != TRADINGVIEW_91_COLUMNS or any(len(r) != len(rows[0]) for r in rows[1:]):
        raise ValueError('TRADINGVIEW_EXPORT_COLUMNS_INVALID')
    symbols = [r[0] for r in rows[1:]]
    labels = [r[1] for r in rows[1:]]
    if any(not x or x != x.strip() for x in symbols + labels):
        raise ValueError('TRADINGVIEW_EXPORT_BLANK_OR_PADDED_IDENTITY')
    if len(symbols) != len(set(symbols)):
        raise ValueError('TRADINGVIEW_EXPORT_DUPLICATE_SYMBOL')
    if any(n > 1 for n in Counter(labels).values()):
        raise ValueError('TRADINGVIEW_EXPORT_AMBIGUOUS_DESCRIPTION')
    bindings = dict(symbol_bindings)
    if (len(bindings) != len(symbol_bindings)
        or len(set(bindings.values())) != len(bindings)
        or any(not k.startswith('NSE:') or not v for k, v in bindings.items())
        or sha256(json.dumps(sorted(symbol_bindings), separators=(',', ':')).encode()).hexdigest() != TRADINGVIEW_91_BINDINGS_SHA256):
        raise ValueError('TRADINGVIEW_EXPORT_GOVERNED_BINDING_INVALID')
    matched = []
    for i, row in enumerate(rows[1:], start=2):
        key = 'NSE:' + row[0]
        if key not in bindings:
            continue
        row_hash = sha256(json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        matched.append(QualifiedEquityLabel(bindings[key], row[0], row[1], i, row_hash))
    return QualifiedTradingViewExport(expected_sha256, len(symbols), tuple(matched),
        tuple(sorted(set(bindings) - {'NSE:' + x for x in symbols})),
        tuple(sorted(x for x in symbols if 'NSE:' + x not in bindings)))


def build_tradingview_equity_successor(
    previous: VisualIdentityRelationshipPublication,
    payload: bytes, *, symbol_bindings: tuple[tuple[str, str], ...],
    canonical_subject_identities: tuple[str, ...],
    effective_from: datetime = TRADINGVIEW_91_RETAINED_AT,
) -> VisualIdentityRelationshipPublication:
    """Retain previous records exactly; add only distinct evidence-backed labels."""
    export = qualify_tradingview_equity_export(payload, symbol_bindings=symbol_bindings)
    if (previous.publication_version != '1.5.0'
        or export.source_sha256 != TRADINGVIEW_91_SOURCE_SHA256
        or export.source_authority != SPONSOR_TRADINGVIEW_EXPORT
        or effective_from != TRADINGVIEW_91_RETAINED_AT):
        raise ValueError('TRADINGVIEW_EXPORT_PUBLICATION_AUTHORITY_INVALID')
    relationships = list(previous.relationships)
    for row in export.matched:
        same_label = [r for r in relationships
            if r.observed_visible_subject_identity == row.description
            and r.source_context is VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART]
        if same_label:
            if len(same_label) != 1 or same_label[0].canonical_subject_identity != row.canonical_identity:
                raise ValueError('TRADINGVIEW_EXPORT_RELATIONSHIP_CONFLICT')
            # Retain earlier authority; do not duplicate overlapping same-label records.
            if not same_label[0].active_at(effective_from):
                raise ValueError('TRADINGVIEW_EXPORT_EXISTING_RELATIONSHIP_INACTIVE')
            continue
        relationships.append(create_visual_identity_relationship(
            canonical_subject_identity=row.canonical_identity,
            observed_visible_subject_identity=row.description,
            source_context=VisualIdentitySourceContext.TRADINGVIEW_VISUAL_CHART,
            effective_from=effective_from, effective_through=previous.effective_through,
            status=VisualIdentityRelationshipStatus.ACTIVE,
            source_identity='SPONSOR-TRADINGVIEW-CSV-SHA256-' + export.source_sha256,
            provenance=('ADR-0018', 'WO-07E-TRADINGVIEW-91-SPONSOR-AUTHORIZATION',
                SPONSOR_TRADINGVIEW_EXPORT, 'TRADINGVIEW-SYMBOL:' + row.symbol,
                'TRADINGVIEW-DESCRIPTION:' + row.description,
                'CSV-SHA256-' + export.source_sha256, 'CSV-ROW-SHA256-' + row.row_sha256,
                'SOURCE-RETAINED-AT-' + effective_from.isoformat(),
                'EXACT-NSE-SYMBOL-BINDING;NO-DESCRIPTION-DERIVED-CANONICAL-IDENTITY'),
            supersedes=None))
    return create_visual_identity_publication(
        canonical_subject_identities=canonical_subject_identities,
        publication_version='1.6.0', effective_from=previous.effective_from,
        effective_through=previous.effective_through,
        source_identities=previous.source_identities + ('SPONSOR-TRADINGVIEW-CSV-SHA256-' + export.source_sha256,),
        provenance=previous.provenance + ('WO-07E-TRADINGVIEW-91-SPONSOR-AUTHORIZATION',
            'OLDER-RELATIONSHIPS-UNCHANGED;EXPORT-ONLY-RELATIONSHIPS-NOT-BACKDATED',
            'NSE-EQUITIES-ONLY;NO-INDEX-OR-MCX-INFERENCE'),
        relationships=tuple(relationships), supersedes=previous.integrity_identity)
