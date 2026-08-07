from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import subprocess
import sys

import pytest

from kronos.configuration.settings import Settings
from kronos.provider.kite.live_activation import (
    ActivationProvenanceKind,
    CanonicalRepositoryEvidence,
    CoordinatedActivationValues,
    DurableConsumptionRecord,
    DurableConsumptionResult,
    LiveActivationError,
    MonotonicLifecycleDeadline,
    ProvenConsumption,
    TrustedActivationReviewer,
)
from kronos.provider.models.authentication import (
    ConsumptionOutcomeCategory,
    CoordinatedConsumptionState,
    GovernedAuthenticationOperation,
    SanitizedOperationLedger,
)
from tools.provider_pilots import car017_live_authentication_launcher as launcher


ROOT = Path(__file__).resolve().parents[3]
SHA = "a" * 40
GOVERNANCE_SHA = "cdaeaf1669e7182f36f9ea753315cf7992843d78"
OPERATIONAL_CORRECTION_SHA = "218b01fa7ed7815f3b7fefb127e278dc3909481b"
SYNTHETIC_CORRECTIVE_SHA = "d" * 40


def _candidate_corrective_sha(document: str | None = None) -> str:
    selected_document = document
    if selected_document is None:
        selected_document = (
            ROOT
            / "docs/governance/reviews/"
            "CAR-018-COMPLETE-PROVIDER-AUTHENTICATION-OPERATIONAL-CLOSURE-"
            "AUTHORIZATION.md"
        ).read_text(encoding="utf-8")
    disposition_count = len(
        re.findall(
            r"^## Approved Canonical post-correction CA2 activation disposition$",
            selected_document,
            re.MULTILINE,
        )
    )
    if disposition_count == 0:
        return SYNTHETIC_CORRECTIVE_SHA
    if disposition_count > 1:
        raise AssertionError("CA2 fixture records are duplicated or ambiguous")
    return launcher._extract_corrective_sha(selected_document, "CA2")


CORRECTIVE_SHA = _candidate_corrective_sha()
LATEST_GOVERNANCE_SHA = "f" * 40
CA2_IDENTITY = "KRONOS-COORD-AUTH-20260806-003"
CA2_CAR016_REF = "CAR-016-V1.2-CA2-KRONOS-COORD-AUTH-20260806-003"
CA2_CAR017_REF = "CAR-017-V1.2-CA2-KRONOS-COORD-AUTH-20260806-003"
NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
LIVE_NOW = datetime(
    2026, 8, 8, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))
)


class _Verifier:
    def __init__(self) -> None:
        self.calls = 0

    def verify(self, expected: object, observed: object, evidence: object) -> bool:
        self.calls += 1
        return expected is observed and evidence is not None


class _CapturingEvidenceVerifier:
    def __init__(self) -> None:
        self.evidence: object | None = None

    def verify(self, expected: object, observed: object, evidence: object) -> bool:
        self.evidence = evidence
        return expected is observed


class _Consumption:
    def __init__(self, *, consumed: bool = True) -> None:
        self.calls = 0
        self.consumed = consumed
        self.kwargs: dict[str, object] = {}

    def consume(self, **kwargs: object) -> DurableConsumptionResult:
        self.calls += 1
        self.kwargs = kwargs
        if not self.consumed:
            return DurableConsumptionResult(
                ConsumptionOutcomeCategory.POST_CONFIRMATION_CONSUMPTION_UNCERTAIN,
                None,
            )
        ledger = kwargs["ledger"]
        assert type(ledger) is SanitizedOperationLedger
        return DurableConsumptionResult(
            ConsumptionOutcomeCategory.CONSUMED,
            ProvenConsumption(
                record=DurableConsumptionRecord(
                    coordinated_activation_identity="KRONOS-TEST-LAUNCH-001",
                    coordinated_governance_publication_sha=SHA,
                    consumed_at=NOW.isoformat(),
                ),
                deadline=MonotonicLifecycleDeadline(monotonic_now=100.0),
                ledger=ledger.record(
                    GovernedAuthenticationOperation.AUTHORITY_CONSUMPTION
                ),
            ),
        )


class _DurableFilesystem:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.payload = b""

    def open_verified_parent_directory(
        self, _directory: str, *, expected_owner: int, expected_mode: int
    ) -> object:
        assert expected_owner == 501
        assert expected_mode == 0o700
        self.events.append("open-parent")
        return object()

    def create_exclusive_nofollow(
        self, _parent: object, _filename: str, *, mode: int
    ) -> object:
        assert mode == 0o600
        self.events.append("create-record")
        return object()

    def verify_open_file(self, _file: object, **_kwargs: object) -> None:
        self.events.append("verify-record")

    def write_all(self, _file: object, payload: bytes) -> None:
        self.payload = payload
        self.events.append("write-record")

    def flush_file(self, _file: object) -> None:
        self.events.append("flush-record")

    def fsync_file(self, _file: object) -> None:
        self.events.append("fsync-record")

    def close_file(self, _file: object) -> None:
        self.events.append("close-record")

    def fsync_directory(self, _parent: object) -> None:
        self.events.append("fsync-parent")

    def close_directory(self, _parent: object) -> None:
        self.events.append("close-parent")


def _values() -> CoordinatedActivationValues:
    return CoordinatedActivationValues(
        coordinated_activation_identity="KRONOS-TEST-LAUNCH-001",
        coordinated_governance_publication_sha=SHA,
        car016_logical_publication_ref="CAR-016-V1.2-TEST",
        car017_logical_publication_ref="CAR-017-V1.2-TEST",
        frozen_car016_implementation_sha="b" * 40,
        frozen_car017_implementation_sha="c" * 40,
        authority_effective_at=NOW - timedelta(hours=1),
        authority_effective_timezone="Asia/Kolkata",
        authority_expires_at=NOW + timedelta(hours=1),
        authority_expiry_timezone="Asia/Kolkata",
        authentication_attempt_timeout_seconds=300,
        sponsor_environment_ref="TEST-NONPROD",
        hostname="test.local",
        provider_identity="ZERODHA_KITE",
        operational_provider="KITE",
        provider_configuration_ref="ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY",
        application_registration_ref="ZERODHA-KITE-APP-REGISTRATION-PRIMARY",
        credential_ref="KITE-API-SECRET-PRIMARY",
        intended_principal_registration_ref="KITE-INTENDED-PRINCIPAL-PRIMARY",
        composition_dependency_set_ref="CAR017-LIVE-COMPOSITION-DEPENDENCY-SET-V1",
        redirect_url="http://127.0.0.1:8765/kite/callback",
        attempt_cardinality="ONE",
        provider_availability_authority="WITHHELD",
        provider_availability_max_operations=0,
        car014_status="UNEXECUTED",
        consumption_state=CoordinatedConsumptionState.UNUSED,
    )


def _request(values: CoordinatedActivationValues) -> launcher.GovernedLaunchRequest:
    return launcher.GovernedLaunchRequest(
        expected=values,
        observed=values,
        repository_evidence=CanonicalRepositoryEvidence(
            branch="develop",
            head_sha=SHA,
            origin_develop_sha=SHA,
            working_tree_clean=True,
            car016_canonical=True,
            car017_canonical=True,
            car014_unexecuted=True,
        ),
        reviewed_at=NOW,
        runtime=launcher.RuntimeVersionEvidence(
            python=(3, 13, 14), tkinter="9.0", kite_sdk="5.2.0"
        ),
    )


def _configuration() -> object:
    return Settings(
        provider="KITE",
        kite_api_key="UNITKEY",
        kite_api_secret="",
        kite_access_token="",
        kite_redirect_url="http://127.0.0.1:8765/kite/callback",
        kite_credential_ref="KITE-API-SECRET-PRIMARY",
        kite_intended_registration_ref="KITE-INTENDED-PRINCIPAL-PRIMARY",
        provider_configuration_ref="ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY",
        kite_application_registration_ref="ZERODHA-KITE-APP-REGISTRATION-PRIMARY",
    ).governed_provider_authentication_configuration()


def _environment() -> dict[str, str]:
    return {
        "KRONOS_PROVIDER": "KITE",
        "KRONOS_KITE_API_KEY": "UNITKEY",
        "KRONOS_KITE_REDIRECT_URL": "http://127.0.0.1:8765/kite/callback",
        "KRONOS_KITE_CREDENTIAL_REF": "KITE-API-SECRET-PRIMARY",
        "KRONOS_KITE_INTENDED_REGISTRATION_REF": (
            "KITE-INTENDED-PRINCIPAL-PRIMARY"
        ),
        "KRONOS_PROVIDER_CONFIGURATION_REF": (
            "ZERODHA-KITE-PROVIDER-CONFIG-PRIMARY"
        ),
        "KRONOS_KITE_APPLICATION_REGISTRATION_REF": (
            "ZERODHA-KITE-APP-REGISTRATION-PRIMARY"
        ),
    }


def _ca2_values() -> CoordinatedActivationValues:
    return replace(
        launcher._historical_activation_context(),
        coordinated_activation_identity=CA2_IDENTITY,
        car016_logical_publication_ref=CA2_CAR016_REF,
        car017_logical_publication_ref=CA2_CAR017_REF,
        authority_effective_at=datetime(
            2026, 8, 7, 9, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))
        ),
        authority_expires_at=datetime(
            2026, 8, 14, 9, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))
        ),
    )


def _ca2_context_rows(
    *, equality: bool = False, corrective_sha: str = CORRECTIVE_SHA
) -> str:
    values = _ca2_values()
    if equality:
        return "\n".join(
            f"| {label} | `{value}` | `{value}` | `{value}` | "
            + (
                "MATCH; replaced by the resulting publication SHA as "
                "post-publication evidence |"
                if label == "CA2 coordinated governance publication commit SHA"
                else "MATCH |"
            )
            for label, value in launcher._context_pairs(
                values, corrective_sha, "CA2"
            )
        )
    return "\n".join(
        f"| {label} | `{value}` |"
        for label, value in launcher._context_pairs(values, corrective_sha, "CA2")
    )


def _canonical_ca2_records(
    historical_records: tuple[str, str, str, str]
) -> tuple[str, str, str, str]:
    car016, car017, car018, register = historical_records
    section_counts = (
        len(
            re.findall(
                r"^# \d+\. Controlled Amendment — CAR-016-V1\.2-CA2$",
                car016,
                re.MULTILINE,
            )
        ),
        len(
            re.findall(
                r"^# \d+\. Controlled Amendment — CAR-017-V1\.2-CA2$",
                car017,
                re.MULTILINE,
            )
        ),
        len(
            re.findall(
                r"^## Approved Canonical post-correction CA2 activation disposition$",
                car018,
                re.MULTILINE,
            )
        ),
    )
    register_rows: dict[str, str] = {}
    for record in ("CAR-016", "CAR-017", "CAR-018"):
        rows = tuple(
            line
            for line in register.splitlines()
            if line.startswith(f"| {record} |")
        )
        if len(rows) != 1:
            raise AssertionError("CA2 fixture records are duplicated or ambiguous")
        register_rows[record] = rows[0]

    register_discriminators = (
        "current CA2 record:",
        "Controlled Amendment: `CAR-016-V1.2-CA2`",
        "Controlled Amendment: `CAR-017-V1.2-CA2`",
        "Controlled Amendment: `CAR-018-V1.2-CA2`",
        CA2_IDENTITY,
        CA2_CAR016_REF,
        CA2_CAR017_REF,
        CORRECTIVE_SHA,
        "previous coordinated identity: `KRONOS-COORD-AUTH-20260804-002`",
        "previous identity disposition: RETIRED FOR EXECUTION — UNUSED",
    )
    register_has_ca2_evidence = any(
        marker in row
        for row in register_rows.values()
        for marker in register_discriminators
    )
    if all(count == 0 for count in section_counts):
        if register_has_ca2_evidence:
            raise AssertionError("CA2 fixture records are duplicated or ambiguous")
        corrective_sha = SYNTHETIC_CORRECTIVE_SHA
    elif all(count == 1 for count in section_counts):
        corrective_sha = _candidate_corrective_sha(car018)
        common_markers = (
            CA2_CAR016_REF,
            CA2_CAR017_REF,
            corrective_sha,
            "previous coordinated identity: `KRONOS-COORD-AUTH-20260804-002`",
            "previous identity disposition: RETIRED FOR EXECUTION — UNUSED",
        )
        record_markers = {
            "CAR-016": ("Controlled Amendment: `CAR-016-V1.2-CA2`",),
            "CAR-017": ("Controlled Amendment: `CAR-017-V1.2-CA2`",),
        }
        for record, row in register_rows.items():
            ca2_record = row.split("; current CA2 record:", 1)[-1]
            identity_count = len(
                re.findall(
                    rf"(?<!-){re.escape(CA2_IDENTITY)}(?!-)", ca2_record
                )
            )
            common_counts = tuple(
                ca2_record.count(marker) for marker in common_markers
            )
            if record == "CAR-018" and "; current CA2 record:" in row:
                specific_markers = (
                    "current CA2 record: post-correction CA2 activation disposition",
                )
            elif record == "CAR-018":
                specific_markers = (
                    "Controlled Amendment: `CAR-018-V1.2-CA2`",
                )
            else:
                specific_markers = record_markers[record]
            specific_counts = tuple(
                row.count(marker) for marker in specific_markers
            )
            if identity_count != 1 or any(
                count != 1 for count in (*common_counts, *specific_counts)
            ):
                raise AssertionError(
                    "CA2 fixture records are duplicated or ambiguous"
                )
        return historical_records
    else:
        raise AssertionError("CA2 fixture records are duplicated or ambiguous")

    car016 += f"""

# 25. Controlled Amendment — CAR-016-V1.2-CA2

**Controlled Amendment ID:** `CAR-016-V1.2-CA2`
**Controlled Amendment Status:** Approved
**Canonical Status:** Canonical Controlled Amendment
**Underlying Canonical Record:** CAR-016 Version 1.2
**Workflow Stage:** Repository Publication
**Frozen CAR-018 Corrective Composite Implementation SHA:** `{corrective_sha}`

| Previous coordinated activation identity | `KRONOS-COORD-AUTH-20260804-002` |
| Previous identity disposition | `RETIRED FOR EXECUTION — UNUSED` |

{_ca2_context_rows(corrective_sha=corrective_sha)}
"""
    car017 += f"""

# 22. Controlled Amendment — CAR-017-V1.2-CA2

**Controlled Amendment ID:** `CAR-017-V1.2-CA2`
**Controlled Amendment Status:** Approved
**Canonical Status:** Canonical Controlled Amendment
**Underlying Canonical Record:** CAR-017 Version 1.2
**Workflow Stage:** Repository Publication
**Frozen CAR-018 Corrective Composite Implementation SHA:** `{corrective_sha}`

| Previous coordinated activation identity | `KRONOS-COORD-AUTH-20260804-002` |
| Previous identity disposition | `RETIRED FOR EXECUTION — UNUSED` |

{_ca2_context_rows(corrective_sha=corrective_sha)}
"""
    car018 += f"""

## Approved Canonical post-correction CA2 activation disposition

**CAR-016 Controlled Amendment:** `CAR-016-V1.2-CA2`
**CAR-017 Controlled Amendment:** `CAR-017-V1.2-CA2`
**Controlled Amendment Status:** Approved
**Canonical Status:** Canonical Controlled Amendment
**Workflow Stage:** Repository Publication
**Frozen CAR-018 Corrective Composite Implementation SHA:** `{corrective_sha}`

| Previous coordinated activation identity | `KRONOS-COORD-AUTH-20260804-002` |
| Previous identity disposition | `RETIRED FOR EXECUTION — UNUSED` |

{_ca2_context_rows(equality=True, corrective_sha=corrective_sha)}
"""
    register_lines = []
    values = _ca2_values()
    common = (
        f"Controlled Amendment: `{{record}}-V1.2-CA2`; "
        "Canonical Status: Canonical Controlled Amendment; "
        f"{values.coordinated_activation_identity}; "
        f"{values.car016_logical_publication_ref}; "
        f"{values.car017_logical_publication_ref}; "
        f"{corrective_sha}; "
        f"{values.authority_effective_at.isoformat()}; "
        f"{values.authority_expires_at.isoformat()}; "
        "attempt cardinality: ONE; consumption state: UNUSED; "
        "Provider Availability Verification Authority: WITHHELD; "
        "maximum operations: 0; CAR-014 UNEXECUTED; "
        "previous coordinated identity: `KRONOS-COORD-AUTH-20260804-002`; "
        "previous identity disposition: RETIRED FOR EXECUTION — UNUSED"
    )
    for line in register.splitlines():
        record = line.split(" |", 1)[0].removeprefix("| ")
        if record in {"CAR-016", "CAR-017", "CAR-018"}:
            line = f"{line[:-1]} {common.format(record=record)} |"
        register_lines.append(line)
    return car016, car017, car018, "\n".join(register_lines) + "\n"


def _historical_ca1_records(
    records: tuple[str, str, str, str]
) -> tuple[str, str, str, str]:
    def remove_ca2_section(
        document: str, heading: str, *, terminal_heading: str | None = None
    ) -> str:
        matches = tuple(re.finditer(heading, document, re.MULTILINE))
        if not matches:
            return document
        if len(matches) != 1:
            raise AssertionError("CA2 fixture records are duplicated or ambiguous")
        start = matches[0].start()
        if terminal_heading is None:
            return document[:start].rstrip("\n") + "\n"
        terminal = re.search(
            terminal_heading, document[matches[0].end() :], re.MULTILINE
        )
        if terminal is None:
            raise AssertionError("CA2 fixture records are duplicated or ambiguous")
        end = matches[0].end() + terminal.start()
        return document[:start] + document[end:]

    car016, car017, car018, register = records
    car016 = remove_ca2_section(
        car016,
        r"^# \d+\. Controlled Amendment — CAR-016-V1\.2-CA2$",
        terminal_heading=r"^# End of Document$",
    )
    car017 = remove_ca2_section(
        car017,
        r"^# \d+\. Controlled Amendment — CAR-017-V1\.2-CA2$",
    )
    car018 = remove_ca2_section(
        car018,
        r"^## Approved Canonical post-correction CA2 activation disposition$",
        terminal_heading=r"^# End of Document$",
    )
    register_lines = []
    for line in register.splitlines():
        if line.startswith(("| CAR-016 |", "| CAR-017 |", "| CAR-018 |")):
            line = line.split("; current CA2 record:", 1)[0].rstrip() + " |"
        register_lines.append(line)
    return car016, car017, car018, "\n".join(register_lines) + "\n"


def _canonical_snapshot(**changes: object) -> launcher.CanonicalRepositorySnapshot:
    repository_records = tuple(
        (ROOT / path).read_text(encoding="utf-8")
        for path in launcher._GOVERNANCE_PATHS
    )
    historical_records = _historical_ca1_records(repository_records)
    activation_records = _canonical_ca2_records(repository_records)
    corrective_sha = launcher._extract_corrective_sha(
        activation_records[2], "CA2"
    )
    snapshot = launcher.CanonicalRepositorySnapshot(
        evidence=CanonicalRepositoryEvidence(
            branch="develop",
            head_sha=LATEST_GOVERNANCE_SHA,
            origin_develop_sha=LATEST_GOVERNANCE_SHA,
            working_tree_clean=True,
            car016_canonical=True,
            car017_canonical=True,
            car014_unexecuted=True,
        ),
        current_branch="develop",
        current_head_sha=LATEST_GOVERNANCE_SHA,
        current_origin_develop_sha=LATEST_GOVERNANCE_SHA,
        current_working_tree_clean=True,
        approved_corrective_implementation_sha=corrective_sha,
        corrective_parent_sha=OPERATIONAL_CORRECTION_SHA,
        operational_correction_parent_sha=GOVERNANCE_SHA,
        corrective_paths=launcher._CORRECTIVE_PATHS,
        activation_governance_publication_sha=LATEST_GOVERNANCE_SHA,
        activation_governance_paths=launcher._GOVERNANCE_PATHS,
        activation_governance_records=activation_records,
        historical_governance_publication_sha=GOVERNANCE_SHA,
        historical_governance_paths=launcher._GOVERNANCE_PATHS,
        historical_governance_records=historical_records,
    )
    return replace(snapshot, **changes)


def _is_verified(snapshot: launcher.CanonicalRepositorySnapshot) -> bool:
    expected = launcher.expected_activation_context(snapshot)
    return launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, snapshot.evidence
    )


def _ca2_absent_records() -> tuple[str, str, str, str]:
    return (
        "# CAR-016 historical record\n",
        "# CAR-017 historical record\n",
        "# CAR-018 historical record\n",
        "| CAR-016 | historical |\n"
        "| CAR-017 | historical |\n"
        "| CAR-018 | historical |\n",
    )


def test_ca2_fixture_synthesizes_only_when_all_ca2_records_are_absent() -> None:
    records = _ca2_absent_records()

    generated = _canonical_ca2_records(records)

    assert generated != records
    assert generated[0].count("Controlled Amendment — CAR-016-V1.2-CA2") == 1
    assert generated[1].count("Controlled Amendment — CAR-017-V1.2-CA2") == 1
    assert generated[2].count(
        "Approved Canonical post-correction CA2 activation disposition"
    ) == 1
    assert all(SYNTHETIC_CORRECTIVE_SHA in document for document in generated)
    assert all(
        row.count(CA2_CAR016_REF) == 1
        for row in generated[3].splitlines()
        if row.startswith(("| CAR-016 |", "| CAR-017 |", "| CAR-018 |"))
    )


def test_ca2_fixture_preserves_exactly_once_records_byte_for_byte() -> None:
    published = _canonical_ca2_records(_ca2_absent_records())

    preserved = _canonical_ca2_records(published)

    assert preserved is published
    assert preserved == published
    car018_row = next(
        line for line in preserved[3].splitlines() if line.startswith("| CAR-018 |")
    )
    assert car018_row.count(
        "Controlled Amendment: `CAR-018-V1.2-CA2`"
    ) == 1


@pytest.mark.parametrize("ambiguity", ["partial", "duplicate"])
def test_ca2_fixture_rejects_partial_or_duplicate_records(ambiguity: str) -> None:
    if ambiguity == "partial":
        records = list(_ca2_absent_records())
        records[0] += "\n# 25. Controlled Amendment — CAR-016-V1.2-CA2\n"
    else:
        records = list(_canonical_ca2_records(_ca2_absent_records()))
        records[0] += "\n# 26. Controlled Amendment — CAR-016-V1.2-CA2\n"

    with pytest.raises(
        AssertionError, match="CA2 fixture records are duplicated or ambiguous"
    ):
        _canonical_ca2_records(tuple(records))  # type: ignore[arg-type]


def test_actual_four_file_ca2_candidate_is_preserved_and_verified() -> None:
    records = tuple(
        (ROOT / path).read_text(encoding="utf-8")
        for path in launcher._GOVERNANCE_PATHS
    )

    assert _canonical_ca2_records(records) is records
    assert _is_verified(_canonical_snapshot()) is True
    car018_row = next(
        line for line in records[3].splitlines() if line.startswith("| CAR-018 |")
    )
    assert car018_row.count(
        "current CA2 record: post-correction CA2 activation disposition"
    ) == 1


def test_corrective_sha_selection_distinguishes_absent_and_valid_ca2() -> None:
    actual_car018 = (
        ROOT / launcher._GOVERNANCE_PATHS[2]
    ).read_text(encoding="utf-8")

    assert _candidate_corrective_sha("# CAR-018 historical record\n") == (
        SYNTHETIC_CORRECTIVE_SHA
    )
    assert _candidate_corrective_sha(actual_car018) == CORRECTIVE_SHA


@pytest.mark.parametrize("defect", ["malformed", "missing", "duplicated"])
def test_corrective_sha_selection_rejects_invalid_ca2_disposition(
    defect: str,
) -> None:
    actual_car018 = (
        ROOT / launcher._GOVERNANCE_PATHS[2]
    ).read_text(encoding="utf-8")
    if defect == "malformed":
        document = actual_car018.replace(
            f"**Frozen CAR-018 Corrective Composite Implementation SHA:** "
            f"`{CORRECTIVE_SHA}`",
            "**Frozen CAR-018 Corrective Composite Implementation SHA:** "
            "`MALFORMED`",
            1,
        )
    elif defect == "missing":
        document = actual_car018.replace(
            f"**Frozen CAR-018 Corrective Composite Implementation SHA:** "
            f"`{CORRECTIVE_SHA}`\n",
            "",
            1,
        )
    else:
        document = actual_car018 + (
            "\n## Approved Canonical post-correction CA2 activation disposition\n"
        )

    expected_error = AssertionError if defect == "duplicated" else RuntimeError
    with pytest.raises(expected_error):
        _candidate_corrective_sha(document)


@pytest.mark.parametrize(
    ("defect", "target"),
    (
        ("only-car016-reference", ""),
        ("missing-car017-reference", CA2_CAR017_REF),
        ("missing-current-identity", CA2_IDENTITY),
        (
            "missing-prior-identity",
            "previous coordinated identity: `KRONOS-COORD-AUTH-20260804-002`",
        ),
        (
            "missing-retirement-disposition",
            "previous identity disposition: RETIRED FOR EXECUTION — UNUSED",
        ),
        ("duplicated-required-marker", CA2_CAR016_REF),
    ),
)
def test_ca2_fixture_rejects_incomplete_or_duplicated_register_markers(
    defect: str, target: str
) -> None:
    records = list(
        tuple(
            (ROOT / path).read_text(encoding="utf-8")
            for path in launcher._GOVERNANCE_PATHS
        )
    )
    if defect == "only-car016-reference":
        records[3] = (
            f"| CAR-016 | {CA2_CAR016_REF} |\n"
            f"| CAR-017 | {CA2_CAR016_REF} |\n"
            f"| CAR-018 | {CA2_CAR016_REF} |\n"
        )
    elif defect == "duplicated-required-marker":
        records[3] = records[3].replace(target, f"{target}; {target}", 1)
    else:
        records[3] = records[3].replace(target, "MISSING", 1)

    with pytest.raises(
        AssertionError, match="CA2 fixture records are duplicated or ambiguous"
    ):
        _canonical_ca2_records(tuple(records))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("record_style", "mutation"),
    (
        ("real", "missing"),
        ("real", "duplicated"),
        ("synthetic", "missing"),
        ("synthetic", "duplicated"),
    ),
)
def test_car018_register_marker_is_required_exactly_once(
    record_style: str, mutation: str
) -> None:
    if record_style == "real":
        records = list(
            tuple(
                (ROOT / path).read_text(encoding="utf-8")
                for path in launcher._GOVERNANCE_PATHS
            )
        )
        marker = "current CA2 record: post-correction CA2 activation disposition"
    else:
        records = list(_canonical_ca2_records(_ca2_absent_records()))
        marker = "Controlled Amendment: `CAR-018-V1.2-CA2`"
    replacement = "MISSING" if mutation == "missing" else f"{marker}; {marker}"
    records[3] = records[3].replace(marker, replacement, 1)

    with pytest.raises(
        AssertionError, match="CA2 fixture records are duplicated or ambiguous"
    ):
        _canonical_ca2_records(tuple(records))  # type: ignore[arg-type]


def test_historical_ca1_derivation_matches_canonical_commit_byte_for_byte() -> None:
    repository_records = tuple(
        (ROOT / path).read_text(encoding="utf-8")
        for path in launcher._GOVERNANCE_PATHS
    )
    historical_records = tuple(
        subprocess.check_output(
            ["git", "show", f"{GOVERNANCE_SHA}:{path}"],
            cwd=ROOT,
            text=True,
        )
        for path in launcher._GOVERNANCE_PATHS
    )

    assert _historical_ca1_records(repository_records) == historical_records


def _prepare(
    *,
    consumption: _Consumption | None = None,
    composition: object | None = None,
) -> tuple[launcher.PreparedGovernedLaunch, _Consumption, list[str]]:
    values = _values()
    events: list[str] = []
    selected_consumption = consumption or _Consumption()

    def compose(*_args: object, **_kwargs: object) -> object:
        events.append("compose")
        return composition or object()

    prepared = launcher.prepare_governed_launch(
        _request(values),
        reviewer=TrustedActivationReviewer(
            _Verifier(), provenance_kind=ActivationProvenanceKind.FAKE_ONLY
        ),
        consumption=selected_consumption,  # type: ignore[arg-type]
        configuration_loader=lambda: _configuration(),  # type: ignore[return-value]
        consumed_at=lambda: NOW,
        monotonic=lambda: 100.0,
        composition_factory=compose,
    )
    return prepared, selected_consumption, events


def test_direct_import_is_silent_and_effect_free() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import tools.provider_pilots.car017_live_authentication_launcher"],
        cwd=ROOT,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_preflight_constructs_no_runtime_dependency_and_does_not_consume() -> None:
    prepared, consumption, events = _prepare()

    assert consumption.calls == 0
    assert events == []
    assert prepared.operation_ledger().count_for(
        GovernedAuthenticationOperation.ACTIVATION_VALIDATION
    ) == 1


def test_confirmation_precedes_consumption_and_composition() -> None:
    prepared, consumption, events = _prepare()

    def gui_main(**kwargs: object) -> None:
        events.append("gui")
        confirmation = kwargs["confirmation"]
        composition = kwargs["composition_factory"]
        activation = kwargs["activation"]
        assert callable(confirmation) and confirmation() is True
        events.append("confirmed")
        assert callable(composition)
        composition(activation)

    launcher.launch_prepared(
        prepared,
        gui_main=gui_main,
        confirmation=lambda: True,
        worker_submit=lambda _operation: None,
    )

    assert consumption.calls == 1
    assert consumption.kwargs["sponsor_confirmed"] is True
    assert events == ["gui", "confirmed", "compose"]
    assert prepared.operation_ledger().count_for(
        GovernedAuthenticationOperation.AUTHORITY_CONSUMPTION
    ) == 1


def test_uncertain_consumption_stops_before_composition() -> None:
    prepared, consumption, events = _prepare(consumption=_Consumption(consumed=False))

    with pytest.raises(RuntimeError, match="POST_CONFIRMATION_CONSUMPTION_UNCERTAIN"):
        prepared.compose_after_confirmation(prepared.activation)

    assert consumption.calls == 1
    assert events == []


def test_runtime_mismatch_fails_before_configuration_and_consumption() -> None:
    values = _values()
    request = launcher.GovernedLaunchRequest(
        expected=values,
        observed=values,
        repository_evidence=_request(values).repository_evidence,
        reviewed_at=NOW,
        runtime=launcher.RuntimeVersionEvidence(
            python=(3, 13, 13), tkinter="9.0", kite_sdk="5.2.0"
        ),
    )
    config_calls = 0

    def config() -> object:
        nonlocal config_calls
        config_calls += 1
        return _configuration()

    with pytest.raises(RuntimeError, match="GOVERNED_RUNTIME_PREFLIGHT_FAILED"):
        launcher.prepare_governed_launch(
            request,
            reviewer=TrustedActivationReviewer(
                _Verifier(), provenance_kind=ActivationProvenanceKind.FAKE_ONLY
            ),
            consumption=_Consumption(),  # type: ignore[arg-type]
            configuration_loader=config,  # type: ignore[arg-type]
            consumed_at=lambda: NOW,
        )
    assert config_calls == 0


def test_launcher_source_has_no_dotenv_or_provider_availability_call() -> None:
    source = Path(launcher.__file__).read_text()

    assert "load_dotenv" not in source
    assert "verify_provider_availability(" not in source
    assert "invalidate_access_token" not in source


def test_production_verifier_accepts_exact_distinct_contexts_and_manifest() -> None:
    snapshot = _canonical_snapshot()
    expected = launcher.expected_activation_context(snapshot)
    observed = launcher.observed_activation_context(
        expected=expected,
        repository_evidence=snapshot.evidence,
        configuration=_configuration(),  # type: ignore[arg-type]
        hostname="Imrans-Mac-mini.local",
    )
    verifier = launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot)

    assert expected is not observed
    assert expected.exactly_matches(observed)
    assert verifier.verify(expected, observed, snapshot.evidence) is True


def test_historical_ca1_and_current_ca2_are_selected_independently() -> None:
    snapshot = _canonical_snapshot()
    expected = launcher.expected_activation_context(snapshot)

    assert launcher._verify_car016_record(
        snapshot.historical_governance_records[0],
        launcher._historical_activation_context(),
        launcher._FROZEN_CAR018_SHA,
        "CA1",
    )
    assert expected.coordinated_activation_identity == CA2_IDENTITY
    assert expected.car016_logical_publication_ref == CA2_CAR016_REF
    assert expected.car017_logical_publication_ref == CA2_CAR017_REF
    assert expected.authority_effective_at.isoformat() == "2026-08-07T09:00:00+05:30"
    assert expected.authority_expires_at.isoformat() == "2026-08-14T09:00:00+05:30"
    assert snapshot.approved_corrective_implementation_sha == CORRECTIVE_SHA


def test_ca1_and_ca2_section_slices_are_exact_and_non_overlapping() -> None:
    document = _canonical_snapshot().activation_governance_records[0]
    ca1 = launcher._amendment_section(document, "CAR-016", "CA1")
    ca2 = launcher._amendment_section(document, "CAR-016", "CA2")

    assert "CAR-016-V1.2-CA2" not in ca1
    assert "CAR-016-V1.2-CA1" not in ca2
    assert ca1 in document and ca2 in document


def test_required_ca1_content_existing_only_in_ca2_does_not_satisfy_ca1() -> None:
    snapshot = _canonical_snapshot()
    ca2 = launcher._amendment_section(
        snapshot.activation_governance_records[0], "CAR-016", "CA2"
    )
    document = "# 1. Controlled Amendment — CAR-016-V1.2-CA1\n\n" + ca2

    assert launcher._verify_car016_record(
        document,
        launcher._historical_activation_context(),
        launcher._FROZEN_CAR018_SHA,
        "CA1",
    ) is False


def test_required_ca2_content_in_later_peer_does_not_satisfy_ca2() -> None:
    snapshot = _canonical_snapshot()
    ca2 = launcher._amendment_section(
        snapshot.activation_governance_records[0], "CAR-016", "CA2"
    )
    body = ca2.split("\n", 1)[1]
    document = (
        "# 25. Controlled Amendment — CAR-016-V1.2-CA2\n\n"
        "# 26. Controlled Amendment — CAR-016-V1.2-CA3\n"
        f"{body}"
    )

    assert launcher._verify_car016_record(
        document, _ca2_values(), CORRECTIVE_SHA, "CA2"
    ) is False


def test_duplicate_metadata_outside_ca2_does_not_count_as_internal() -> None:
    snapshot = _canonical_snapshot()
    document = snapshot.activation_governance_records[0] + (
        "\n# 26. Controlled Amendment — CAR-016-V1.2-CA3\n"
        "**Controlled Amendment Status:** Approved\n"
    )

    assert launcher._verify_car016_record(
        document, _ca2_values(), CORRECTIVE_SHA, "CA2"
    ) is True


def test_duplicate_metadata_inside_ca2_fails() -> None:
    snapshot = _canonical_snapshot()
    records = list(snapshot.activation_governance_records)
    records[0] += "\n**Controlled Amendment Status:** Approved\n"
    altered = replace(snapshot, activation_governance_records=tuple(records))

    assert _is_verified(altered) is False


def test_later_post_attempt_peer_content_does_not_alter_ca2_parsing() -> None:
    snapshot = _canonical_snapshot()
    document = snapshot.activation_governance_records[2] + (
        "\n## Approved Canonical post-attempt activation disposition\n"
        "**Frozen CAR-018 Corrective Composite Implementation SHA:** `"
        + ("e" * 40)
        + "`\n"
    )

    assert launcher._extract_corrective_sha(document, "CA2") == CORRECTIVE_SHA
    assert launcher._verify_car018_record(
        document, _ca2_values(), CORRECTIVE_SHA, "CA2"
    ) is True


def test_exact_retired_predecessor_is_verified_across_all_current_records() -> None:
    assert _is_verified(_canonical_snapshot()) is True


@pytest.mark.parametrize(
    "predecessor",
    (
        "KRONOS-COORD-AUTH-UNKNOWN",
        "",
        CA2_IDENTITY,
        "kronos-coord-auth-20260804-002",
    ),
)
def test_invalid_car016_retired_predecessor_is_rejected(predecessor: str) -> None:
    snapshot = _canonical_snapshot()
    records = list(snapshot.activation_governance_records)
    records[0] = records[0].replace(
        "| Previous coordinated activation identity | "
        "`KRONOS-COORD-AUTH-20260804-002` |",
        f"| Previous coordinated activation identity | `{predecessor}` |",
    )
    altered = replace(snapshot, activation_governance_records=tuple(records))

    assert _is_verified(altered) is False


@pytest.mark.parametrize("record_index", (1, 2))
def test_cross_record_retired_predecessor_mismatch_is_rejected(
    record_index: int,
) -> None:
    snapshot = _canonical_snapshot()
    records = list(snapshot.activation_governance_records)
    records[record_index] = records[record_index].replace(
        "| Previous coordinated activation identity | "
        "`KRONOS-COORD-AUTH-20260804-002` |",
        "| Previous coordinated activation identity | `KRONOS-WRONG` |",
    )
    altered = replace(snapshot, activation_governance_records=tuple(records))

    assert _is_verified(altered) is False


def test_register_predecessor_mismatch_is_rejected() -> None:
    snapshot = _canonical_snapshot()
    records = list(snapshot.activation_governance_records)
    records[3] = records[3].replace(
        "previous coordinated identity: `KRONOS-COORD-AUTH-20260804-002`",
        "previous coordinated identity: `KRONOS-WRONG`",
        1,
    )
    altered = replace(snapshot, activation_governance_records=tuple(records))

    assert _is_verified(altered) is False


def test_altered_predecessor_disposition_is_rejected() -> None:
    snapshot = _canonical_snapshot()
    records = list(snapshot.activation_governance_records)
    records[0] = records[0].replace(
        "| Previous identity disposition | `RETIRED FOR EXECUTION — UNUSED` |",
        "| Previous identity disposition | `RETIRED` |",
    )
    altered = replace(snapshot, activation_governance_records=tuple(records))

    assert _is_verified(altered) is False


def test_current_publication_with_only_ca1_fails_closed() -> None:
    snapshot = _canonical_snapshot(
        activation_governance_records=_canonical_snapshot().historical_governance_records
    )

    with pytest.raises(RuntimeError, match="GOVERNED_ACTIVATION_AMENDMENT_INVALID"):
        launcher.expected_activation_context(snapshot)


def test_draft_or_ambiguous_ca2_status_is_rejected() -> None:
    snapshot = _canonical_snapshot()
    records = list(snapshot.activation_governance_records)
    records[0] = records[0].replace(
        "**Controlled Amendment Status:** Approved",
        "**Controlled Amendment Status:** Draft",
    )
    draft = replace(snapshot, activation_governance_records=tuple(records))
    assert _is_verified(draft) is False

    records = list(snapshot.activation_governance_records)
    records[0] += "\n**Controlled Amendment Status:** Approved\n"
    ambiguous = replace(snapshot, activation_governance_records=tuple(records))
    assert _is_verified(ambiguous) is False


def test_duplicate_ca2_section_or_corrective_binding_is_rejected() -> None:
    snapshot = _canonical_snapshot()
    records = list(snapshot.activation_governance_records)
    section = launcher._amendment_section(records[0], "CAR-016", "CA2")
    records[0] += "\n" + section
    duplicate_section = replace(snapshot, activation_governance_records=tuple(records))
    with pytest.raises(RuntimeError, match="GOVERNED_ACTIVATION_AMENDMENT_INVALID"):
        launcher.expected_activation_context(duplicate_section)

    records = list(snapshot.activation_governance_records)
    records[2] += (
        "\n**Frozen CAR-018 Corrective Composite Implementation SHA:** "
        f"`{CORRECTIVE_SHA}`\n"
    )
    duplicate_sha = replace(snapshot, activation_governance_records=tuple(records))
    assert _is_verified(duplicate_sha) is False


def test_ca1_labels_inside_ca2_and_ca2_reference_mismatch_are_rejected() -> None:
    snapshot = _canonical_snapshot()
    records = list(snapshot.activation_governance_records)
    records[0] = records[0].replace(
        "Logical CAR-016 CA2 publication reference",
        "Logical CAR-016 CA1 publication reference",
        1,
    )
    substituted = replace(snapshot, activation_governance_records=tuple(records))
    with pytest.raises(RuntimeError, match="GOVERNED_ACTIVATION_RECORD_INVALID"):
        launcher.expected_activation_context(substituted)

    records = list(snapshot.activation_governance_records)
    records[1] = records[1].replace(CA2_CAR017_REF, "CAR-017-V1.2-CA2-WRONG", 1)
    mismatched = replace(snapshot, activation_governance_records=tuple(records))
    assert _is_verified(mismatched) is False


def test_ca2_cross_record_identity_matrix_and_register_mismatches_are_rejected() -> None:
    snapshot = _canonical_snapshot()
    for index in (1, 2, 3):
        records = list(snapshot.activation_governance_records)
        records[index] = records[index].replace(CA2_IDENTITY, "KRONOS-WRONG")
        altered = replace(snapshot, activation_governance_records=tuple(records))
        assert _is_verified(altered) is False


def test_retired_identity_and_historical_corrective_sha_cannot_be_current() -> None:
    snapshot = _canonical_snapshot()
    records = tuple(
        document.replace(CA2_IDENTITY, "KRONOS-COORD-AUTH-20260804-002")
        for document in snapshot.activation_governance_records
    )
    retired = replace(snapshot, activation_governance_records=records)
    assert _is_verified(retired) is False

    records = tuple(
        document.replace(CORRECTIVE_SHA, launcher._FROZEN_CAR018_SHA)
        for document in snapshot.activation_governance_records
    )
    historical = replace(
        snapshot,
        approved_corrective_implementation_sha=launcher._FROZEN_CAR018_SHA,
        activation_governance_records=records,
    )
    assert _is_verified(historical) is False


@pytest.mark.parametrize(
    "reviewed_at",
    (
        datetime(
            2026, 8, 7, 8, 59, 59, tzinfo=timezone(timedelta(hours=5, minutes=30))
        ),
        datetime(
            2026, 8, 14, 9, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))
        ),
    ),
)
def test_pre_effective_or_expired_ca2_window_is_rejected(
    reviewed_at: datetime,
) -> None:
    snapshot = _canonical_snapshot()
    expected = launcher.expected_activation_context(snapshot)
    reviewer = TrustedActivationReviewer(
        launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot),
        provenance_kind=ActivationProvenanceKind.CANONICAL_LIVE,
    )

    with pytest.raises(LiveActivationError, match="OUTSIDE_AUTHORITY_WINDOW"):
        reviewer.review(
            expected=expected,
            observed=expected,
            repository_evidence=snapshot.evidence,
            reviewed_at=reviewed_at,
        )


@pytest.mark.parametrize(
    ("label", "replacement"),
    (
        (
            "| Maximum Provider Availability verification operations | `0` |",
            "| Maximum Provider Availability verification operations | `1` |",
        ),
        (
            "| CAR-014 status | `UNEXECUTED` |",
            "| CAR-014 status | `EXECUTED` |",
        ),
    ),
)
def test_prohibited_ca2_authority_values_fail_closed(
    label: str, replacement: str
) -> None:
    snapshot = _canonical_snapshot()
    records = list(snapshot.activation_governance_records)
    records[0] = records[0].replace(label, replacement)
    altered = replace(snapshot, activation_governance_records=tuple(records))
    with pytest.raises(LiveActivationError, match="INVALID_CONTEXT"):
        launcher.expected_activation_context(altered)


def test_current_activation_context_uses_latest_governance_publication_sha() -> None:
    snapshot = _canonical_snapshot()

    assert (
        launcher.expected_activation_context(snapshot).coordinated_governance_publication_sha
        == LATEST_GOVERNANCE_SHA
    )


def test_trusted_reviewer_receives_current_repository_evidence() -> None:
    snapshot = _canonical_snapshot()
    expected = launcher.expected_activation_context(snapshot)
    verifier = _CapturingEvidenceVerifier()
    reviewer = TrustedActivationReviewer(
        verifier,  # type: ignore[arg-type]
        provenance_kind=ActivationProvenanceKind.CANONICAL_LIVE,
    )

    reviewer.review(
        expected=expected,
        observed=expected,
        repository_evidence=snapshot.evidence,
        reviewed_at=LIVE_NOW,
    )

    assert verifier.evidence is snapshot.evidence
    assert snapshot.evidence.head_sha == LATEST_GOVERNANCE_SHA
    assert snapshot.evidence.origin_develop_sha == LATEST_GOVERNANCE_SHA


def test_production_verifier_rejects_non_governance_publication_manifest() -> None:
    snapshot = _canonical_snapshot(
        activation_governance_paths=(
            "tools/provider_pilots/car017_live_authentication_launcher.py",
        )
    )
    expected = launcher.expected_activation_context(snapshot)
    verifier = launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot)

    assert verifier.verify(expected, expected, snapshot.evidence) is False


def test_head_cannot_substitute_for_governance_publication_sha() -> None:
    snapshot = _canonical_snapshot()
    substituted = replace(
        launcher.expected_activation_context(snapshot),
        coordinated_governance_publication_sha=CORRECTIVE_SHA,
    )
    substituted_evidence = replace(
        snapshot.evidence,
        head_sha=CORRECTIVE_SHA,
        origin_develop_sha=CORRECTIVE_SHA,
    )

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        substituted,
        substituted,
        substituted_evidence,
    ) is False


def test_historical_sha_cannot_substitute_in_current_activation_context() -> None:
    snapshot = _canonical_snapshot()
    substituted = replace(
        launcher.expected_activation_context(snapshot),
        coordinated_governance_publication_sha=GOVERNANCE_SHA,
    )

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        substituted, substituted, snapshot.evidence
    ) is False


def test_historical_sha_cannot_substitute_in_current_repository_evidence() -> None:
    snapshot = _canonical_snapshot()
    expected = launcher.expected_activation_context(snapshot)
    historical_evidence = replace(
        snapshot.evidence,
        head_sha=GOVERNANCE_SHA,
        origin_develop_sha=GOVERNANCE_SHA,
    )

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, historical_evidence
    ) is False


def test_wrong_governance_publication_sha_is_rejected() -> None:
    wrong = "e" * 40
    snapshot = _canonical_snapshot(
        historical_governance_publication_sha=wrong,
        evidence=replace(
            _canonical_snapshot().evidence,
            head_sha=wrong,
            origin_develop_sha=wrong,
        ),
    )
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected,
        expected,
        snapshot.evidence,
    ) is False


def test_wrong_corrective_implementation_sha_is_rejected() -> None:
    snapshot = _canonical_snapshot(approved_corrective_implementation_sha="e" * 40)
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected,
        expected,
        snapshot.evidence,
    ) is False


def test_missing_approved_corrective_implementation_sha_is_rejected() -> None:
    snapshot = _canonical_snapshot(approved_corrective_implementation_sha="")
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, snapshot.evidence
    ) is False


def test_corrective_sha_absent_from_activation_records_is_rejected() -> None:
    snapshot = _canonical_snapshot()
    records = tuple(
        document.replace(CORRECTIVE_SHA, "MISSING")
        for document in snapshot.activation_governance_records
    )
    altered = replace(snapshot, activation_governance_records=records)
    expected = launcher.expected_activation_context(altered)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(altered).verify(
        expected, expected, altered.evidence
    ) is False


@pytest.mark.parametrize("record_index", (0, 1, 2, 3))
def test_ca2_corrective_sha_must_match_every_record(record_index: int) -> None:
    snapshot = _canonical_snapshot()
    records = list(snapshot.activation_governance_records)
    records[record_index] = records[record_index].replace(
        CORRECTIVE_SHA, "e" * 40
    )
    altered = replace(snapshot, activation_governance_records=tuple(records))

    assert _is_verified(altered) is False


def test_current_head_cannot_stand_in_for_latest_activation_governance() -> None:
    snapshot = _canonical_snapshot(
        current_head_sha=CORRECTIVE_SHA,
        current_origin_develop_sha=CORRECTIVE_SHA,
    )
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, snapshot.evidence
    ) is False


def test_current_head_must_equal_latest_activation_governance_publication() -> None:
    snapshot = _canonical_snapshot(
        current_head_sha="e" * 40,
        current_origin_develop_sha="e" * 40,
    )
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, snapshot.evidence
    ) is False


def test_approved_corrective_sha_cannot_be_substituted_with_ambient_head() -> None:
    snapshot = _canonical_snapshot(
        approved_corrective_implementation_sha=LATEST_GOVERNANCE_SHA,
        corrective_parent_sha=OPERATIONAL_CORRECTION_SHA,
    )
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, snapshot.evidence
    ) is False


def test_corrective_parent_mismatch_is_rejected() -> None:
    snapshot = _canonical_snapshot(corrective_parent_sha="e" * 40)
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, snapshot.evidence
    ) is False


def test_historical_parent_cannot_replace_parser_alignment_parent() -> None:
    snapshot = _canonical_snapshot(corrective_parent_sha=GOVERNANCE_SHA)

    assert _is_verified(snapshot) is False


def test_operational_correction_parent_must_be_historical_governance() -> None:
    snapshot = _canonical_snapshot(operational_correction_parent_sha="e" * 40)

    assert _is_verified(snapshot) is False


def test_approved_multicommit_governed_ancestry_is_accepted() -> None:
    snapshot = _canonical_snapshot()

    assert snapshot.historical_governance_publication_sha == GOVERNANCE_SHA
    assert snapshot.operational_correction_parent_sha == GOVERNANCE_SHA
    assert snapshot.corrective_parent_sha == OPERATIONAL_CORRECTION_SHA
    assert snapshot.approved_corrective_implementation_sha == CORRECTIVE_SHA
    assert snapshot.activation_governance_publication_sha == LATEST_GOVERNANCE_SHA
    assert _is_verified(snapshot) is True


def test_corrective_manifest_mismatch_is_rejected() -> None:
    snapshot = _canonical_snapshot(corrective_paths=launcher._CORRECTIVE_PATHS[:-1])
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, snapshot.evidence
    ) is False


def test_activation_governance_publication_sha_mismatch_is_rejected() -> None:
    snapshot = _canonical_snapshot(activation_governance_publication_sha="e" * 40)
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, snapshot.evidence
    ) is False


def test_governance_manifest_missing_required_file_is_rejected() -> None:
    snapshot = _canonical_snapshot(
        activation_governance_paths=launcher._GOVERNANCE_PATHS[:-1]
    )
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected,
        expected,
        snapshot.evidence,
    ) is False


def test_governance_manifest_with_unexpected_fifth_file_is_rejected() -> None:
    snapshot = _canonical_snapshot(
        activation_governance_paths=(
            *launcher._GOVERNANCE_PATHS,
            "docs/governance/reviews/UNEXPECTED.md",
        )
    )
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected,
        expected,
        snapshot.evidence,
    ) is False


def test_historical_governance_manifest_is_verified_independently() -> None:
    snapshot = _canonical_snapshot(
        historical_governance_paths=launcher._GOVERNANCE_PATHS[:-1]
    )
    expected = launcher.expected_activation_context(snapshot)

    assert launcher.ProductionCanonicalActivationEvidenceVerifier(snapshot).verify(
        expected, expected, snapshot.evidence
    ) is False


def test_record_specific_metadata_and_register_rows_are_required() -> None:
    snapshot = _canonical_snapshot()
    expected = launcher.expected_activation_context(snapshot)
    records = list(snapshot.activation_governance_records)
    records[0] = records[0].replace(
        "**Controlled Amendment ID:** `CAR-016-V1.2-CA2`",
        "**Controlled Amendment ID:** `CAR-016-V1.2-WRONG`",
        1,
    )
    altered_car = replace(snapshot, activation_governance_records=tuple(records))
    assert launcher.ProductionCanonicalActivationEvidenceVerifier(altered_car).verify(
        expected,
        expected,
        altered_car.evidence,
    ) is False

    records = list(snapshot.activation_governance_records)
    records[3] = records[3].replace(
        "Controlled Amendment: `CAR-017-V1.2-CA2`",
        "Controlled Amendment: `CAR-017-V1.2-WRONG`",
        1,
    )
    altered_register = replace(snapshot, activation_governance_records=tuple(records))
    assert launcher.ProductionCanonicalActivationEvidenceVerifier(
        altered_register
    ).verify(expected, expected, altered_register.evidence) is False


def test_snapshot_reads_four_independent_repository_identities() -> None:
    calls: list[tuple[str, ...]] = []
    repository_records = tuple(
        (ROOT / path).read_text(encoding="utf-8")
        for path in launcher._GOVERNANCE_PATHS
    )
    historical_records = dict(
        zip(
            launcher._GOVERNANCE_PATHS,
            _historical_ca1_records(repository_records),
            strict=True,
        )
    )
    activation_records = dict(
        zip(
            launcher._GOVERNANCE_PATHS,
            _canonical_ca2_records(repository_records),
            strict=True,
        )
    )

    def git_output(arguments: tuple[str, ...]) -> str:
        calls.append(arguments)
        if arguments == ("branch", "--show-current"):
            return "develop\n"
        if arguments == ("rev-parse", "HEAD"):
            return f"{LATEST_GOVERNANCE_SHA}\n"
        if arguments == ("rev-parse", "origin/develop"):
            return f"{LATEST_GOVERNANCE_SHA}\n"
        if arguments == ("status", "--porcelain"):
            return ""
        if arguments == ("rev-parse", f"{CORRECTIVE_SHA}^"):
            return f"{OPERATIONAL_CORRECTION_SHA}\n"
        if arguments == (
            "rev-parse",
            f"{OPERATIONAL_CORRECTION_SHA}^",
        ):
            return f"{GOVERNANCE_SHA}\n"
        if arguments[0] == "diff-tree" and arguments[-1] == LATEST_GOVERNANCE_SHA:
            return "\n".join(launcher._GOVERNANCE_PATHS) + "\n"
        if arguments[0] == "diff-tree" and arguments[-1] == CORRECTIVE_SHA:
            return "\n".join(launcher._CORRECTIVE_PATHS) + "\n"
        if arguments[0] == "diff-tree":
            return "\n".join(launcher._GOVERNANCE_PATHS) + "\n"
        if arguments[0] == "show":
            commit, path = arguments[1].split(":", 1)
            return (
                activation_records[path]
                if commit == LATEST_GOVERNANCE_SHA
                else historical_records[path]
            )
        raise AssertionError(arguments)

    snapshot = launcher.canonical_repository_snapshot(
        ROOT,
        activation_governance_publication_sha=LATEST_GOVERNANCE_SHA,
        git_output=git_output,
    )

    assert snapshot.current_head_sha == LATEST_GOVERNANCE_SHA
    assert snapshot.evidence.head_sha == LATEST_GOVERNANCE_SHA
    assert snapshot.evidence.origin_develop_sha == LATEST_GOVERNANCE_SHA
    assert snapshot.activation_governance_publication_sha == LATEST_GOVERNANCE_SHA
    assert snapshot.approved_corrective_implementation_sha == CORRECTIVE_SHA
    assert snapshot.corrective_parent_sha == OPERATIONAL_CORRECTION_SHA
    assert snapshot.operational_correction_parent_sha == GOVERNANCE_SHA
    assert snapshot.historical_governance_publication_sha == GOVERNANCE_SHA
    assert (
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        GOVERNANCE_SHA,
    ) in calls


def test_post_correction_committed_state_preflight_passes_and_is_inert() -> None:
    events: list[str] = []
    presented: list[str] = []
    filesystem = _DurableFilesystem(events)

    def gui_main(**_kwargs: object) -> None:
        events.append("gui")

    prepared = launcher.execute_governed_launcher(
        repository_root=ROOT,
        environment=_environment(),
        hostname="Imrans-Mac-mini.local",
        reviewed_at=LIVE_NOW,
        runtime=launcher.RuntimeVersionEvidence(
            python=(3, 13, 14), tkinter="9.0", kite_sdk="5.2.0"
        ),
        snapshot=_canonical_snapshot(),
        sponsor_home="/fake-sponsor-home",
        sponsor_user_id=501,
        durable_state=(True, True),
        port_ready_without_bind=True,
        preflight_presenter=presented.append,
        confirmation=lambda: True,
        gui_main=gui_main,
        worker_submit=lambda _operation: None,
        monotonic=lambda: 100.0,
        consumed_at=lambda: LIVE_NOW,
        composition_factory=lambda *_args, **_kwargs: events.append("compose"),
        filesystem=filesystem,
    )

    assert events == ["gui"]
    assert filesystem.payload == b""
    assert presented[0].startswith("GOVERNED LIVE PREFLIGHT EVIDENCE PACKAGE")
    assert "Overall: READY FOR FINAL SPONSOR CONFIRMATION" in presented[0]
    assert presented[1].startswith("SANITIZED GOVERNED TERMINAL EVIDENCE")
    assert prepared.operation_ledger().count_for(
        GovernedAuthenticationOperation.AUTHORITY_CONSUMPTION
    ) == 0


def test_operational_path_consumes_before_exact_live_composition() -> None:
    events: list[str] = []
    filesystem = _DurableFilesystem(events)
    received: dict[str, object] = {}

    def composition(_activation: object, **kwargs: object) -> object:
        events.append("compose")
        received.update(kwargs)
        return object()

    def gui_main(**kwargs: object) -> None:
        events.append("gui")
        confirmation = kwargs["confirmation"]
        compose = kwargs["composition_factory"]
        assert callable(confirmation) and confirmation() is True
        events.append("confirmed")
        assert callable(compose)
        compose(kwargs["activation"])

    prepared = launcher.execute_governed_launcher(
        repository_root=ROOT,
        environment=_environment(),
        hostname="Imrans-Mac-mini.local",
        reviewed_at=LIVE_NOW,
        runtime=launcher.RuntimeVersionEvidence(
            python=(3, 13, 14), tkinter="9.0", kite_sdk="5.2.0"
        ),
        snapshot=_canonical_snapshot(),
        sponsor_home="/fake-sponsor-home",
        sponsor_user_id=501,
        durable_state=(True, True),
        port_ready_without_bind=True,
        preflight_presenter=lambda _evidence: None,
        confirmation=lambda: True,
        gui_main=gui_main,
        worker_submit=lambda _operation: None,
        monotonic=lambda: 100.0,
        consumed_at=lambda: LIVE_NOW,
        composition_factory=composition,
        filesystem=filesystem,
    )

    assert events[:2] == ["gui", "confirmed"]
    assert events.index("confirmed") < events.index("open-parent")
    assert events.index("fsync-parent") < events.index("compose")
    assert type(received["proven_consumption"]) is ProvenConsumption
    assert received["activation_capability"]._is_live_capable() is True
    assert received["operation_recorder"].snapshot() is (
        received["proven_consumption"].ledger
    )
    assert prepared.operation_ledger().count_for(
        GovernedAuthenticationOperation.AUTHORITY_CONSUMPTION
    ) == 1
    assert prepared.operation_ledger().count_for(
        GovernedAuthenticationOperation.PROVIDER_AVAILABILITY_VERIFICATION
    ) == 0


@pytest.mark.parametrize(
    ("durable_state", "port_ready"),
    (((False, False), True), ((True, False), True), ((True, True), False)),
)
def test_failed_preflight_never_launches_or_consumes(
    durable_state: tuple[bool, bool], port_ready: bool
) -> None:
    events: list[str] = []
    filesystem = _DurableFilesystem(events)

    with pytest.raises(RuntimeError, match="GOVERNED_RUNTIME_PREFLIGHT_FAILED"):
        launcher.execute_governed_launcher(
            repository_root=ROOT,
            environment=_environment(),
            hostname="Imrans-Mac-mini.local",
            reviewed_at=LIVE_NOW,
            runtime=launcher.RuntimeVersionEvidence(
                python=(3, 13, 14), tkinter="9.0", kite_sdk="5.2.0"
            ),
            snapshot=_canonical_snapshot(),
            sponsor_home="/fake-sponsor-home",
            sponsor_user_id=501,
            durable_state=durable_state,
            port_ready_without_bind=port_ready,
            preflight_presenter=lambda _evidence: None,
            confirmation=lambda: True,
            gui_main=lambda **_kwargs: events.append("gui"),
            worker_submit=lambda _operation: None,
            monotonic=lambda: 100.0,
            consumed_at=lambda: LIVE_NOW,
            composition_factory=lambda *_args, **_kwargs: events.append("compose"),
            filesystem=filesystem,
        )

    assert events == []
    assert filesystem.payload == b""


def test_terminal_evidence_is_presented_when_gui_terminates_with_failure() -> None:
    presented: list[str] = []

    def gui_main(**_kwargs: object) -> None:
        raise RuntimeError("SYNTHETIC_GUI_FAILURE")

    with pytest.raises(RuntimeError, match="SYNTHETIC_GUI_FAILURE"):
        launcher.execute_governed_launcher(
            repository_root=ROOT,
            environment=_environment(),
            hostname="Imrans-Mac-mini.local",
            reviewed_at=LIVE_NOW,
            runtime=launcher.RuntimeVersionEvidence(
                python=(3, 13, 14), tkinter="9.0", kite_sdk="5.2.0"
            ),
            snapshot=_canonical_snapshot(),
            sponsor_home="/fake-sponsor-home",
            sponsor_user_id=501,
            durable_state=(True, True),
            port_ready_without_bind=True,
            preflight_presenter=presented.append,
            confirmation=lambda: True,
            gui_main=gui_main,
            worker_submit=lambda _operation: None,
            monotonic=lambda: 100.0,
            consumed_at=lambda: LIVE_NOW,
            filesystem=_DurableFilesystem([]),
        )

    assert len(presented) == 2
    assert presented[1].startswith("SANITIZED GOVERNED TERMINAL EVIDENCE")


def test_main_routes_through_operational_assembly(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    snapshot = _canonical_snapshot()
    sponsor = type("Sponsor", (), {"pw_dir": "/fake", "pw_uid": 501})()
    monkeypatch.setattr(
        launcher,
        "canonical_repository_snapshot",
        lambda _root, **_kwargs: snapshot,
    )
    monkeypatch.setenv(
        "KRONOS_ACTIVATION_GOVERNANCE_PUBLICATION_SHA",
        LATEST_GOVERNANCE_SHA,
    )
    monkeypatch.setattr(launcher.pwd, "getpwuid", lambda _uid: sponsor)
    monkeypatch.setattr(launcher, "runtime_version_evidence", lambda: object())
    monkeypatch.setattr(launcher, "_durable_state", lambda *_args: (True, True))
    monkeypatch.setattr(launcher, "_port_ready_without_bind", lambda: True)

    def execute(**_kwargs: object) -> object:
        calls.append("execute-governed-launcher")
        return object()

    monkeypatch.setattr(launcher, "execute_governed_launcher", execute)

    assert launcher.main() == 0
    assert calls == ["execute-governed-launcher"]
