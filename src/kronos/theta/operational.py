"""TE-09R explicit isolated Theta composition; no default-runtime enrollment.

Operational ownership is not analytical authority. Exact retained CA evidence
and methodology publications remain the admission owners. No operation runs on
construction other than preflight and publication of an empty-root ownership file.
"""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import os
import stat

from reportlab.lib.utils import ImageReader

from kronos.market.option_authority import OptionAuthorityReview
from kronos.theta.assessment import ThetaAssessmentEngine
from kronos.theta.contracts import SUBJECTS, digest, encode, parse, require
from kronos.theta.methodology import ThetaMethodologyPublication
from kronos.theta.orchestration import ThetaSponsorWorkflow
from kronos.theta.producer_v3 import V3QuestionProducer
from kronos.theta.store import ThetaStore, directory, read_at, write_at
from kronos.theta.target_authority import OwnerOptionAuthority, ThetaTargetAuthorityAdapter
from kronos.theta.workflow import CHART_ROLES, MAX_CHART_BYTES, ThetaWorkflow

REPOSITORY = Path(__file__).resolve().parents[3]
GENUINE_ROOT = REPOSITORY / "output/theta-te09b-genuine-trial"
SPONSOR_ROOT = Path("/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/Theta Earners")
REVIEW_SHA256 = "4c297cde5c09b7c96b57707137ad21c14c0ae94091a9f8b785f9f0194d06dca0"
CURRENT_SHA256 = "bfd2f9c50c823455e124cccf50722d05a92cacaf8665d6b6968d1327940dda1d"
INSTRUMENT_REFERENCE = "KRONOS-MCX-OPTION-SERIES-2026/2026.2.0/SHA256:6fb82deb2485d1098f848257b23417caf494eece91fbdeced7988edab284a97e"
MARKET_REFERENCE = "KRONOS-MCX-OPTION-EXPIRY-2026/2026.2.0/SHA256:c34f63e6c59c8c02edb0d21ebeeef1479583e6653422bc2b73bd0213c3adde05"
OWNERSHIP = "theta-operational.json"


@dataclass(frozen=True)
class TrialPaths:
    root: Path
    inbox: Path
    outbox: Path
    mode: str

    def validate(self):
        require(self.mode in {"GENUINE_TRIAL", "SYNTHETIC_REHEARSAL"}, "THETA_TRIAL_MODE_INVALID")
        paths = (self.root, self.inbox, self.outbox)
        require(all(isinstance(p, Path) and p.is_absolute() and len(p.parts) > 3
                    and p == Path(os.path.normpath(str(p))) for p in paths), "THETA_TRIAL_PATH_INVALID")
        require(len(set(paths)) == 3 and not any(a in b.parents or b in a.parents
                    for a,b in ((self.root,self.inbox),(self.root,self.outbox),(self.inbox,self.outbox))),
                "THETA_TRIAL_PATH_INVALID")
        if self.mode == "GENUINE_TRIAL":
            require(self.root == GENUINE_ROOT and self.inbox == SPONSOR_ROOT / "CHATGPT ANSWERS"
                    and self.outbox == SPONSOR_ROOT / "KRONOS QUESTIONS", "THETA_TRIAL_PATH_INVALID")
        else:
            require(self.root != GENUINE_ROOT and SPONSOR_ROOT not in self.root.parents
                    and all(SPONSOR_ROOT != p and SPONSOR_ROOT not in p.parents for p in paths),
                    "THETA_TRIAL_PATH_INVALID")
            require(all(any(base in p.parents for base in
                    (Path('/private/tmp'),Path('/private/var/folders'),Path('/tmp'))) for p in paths),
                    "THETA_TRIAL_PATH_INVALID")
        if self.root.exists():
            info=self.root.lstat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid()
                    and stat.S_IMODE(info.st_mode)&0o077==0, "THETA_TRIAL_PERMISSION_INVALID")
        for p in paths:
            with directory(p.parent):
                pass
        # Inbox/outbox must be pre-created owned writable/readable directories.
        # No startup provisioning of Sponsor folders or permission repairs.
        for p, flags in ((self.inbox, os.R_OK | os.X_OK), (self.outbox, os.R_OK | os.W_OK | os.X_OK)):
            with directory(p):
                require(os.access(p, flags), "THETA_TRIAL_PERMISSION_INVALID")
            require(p.stat().st_uid == os.getuid() and stat.S_IMODE(p.stat().st_mode) & 0o077 == 0,
                    "THETA_TRIAL_PERMISSION_INVALID")
        return self


def reviewed_owner():
    """Admission derives from the exact retained CA record, not caller flags."""
    # Approved static owner review travels with source, never trial evidence.
    with directory(REPOSITORY / "data/market_calendars/mcx_option_expiries") as fd:
        raw = read_at(fd, "ca-final-domain-review.json")
    require(digest(raw) == REVIEW_SHA256, "THETA_TRIAL_CA_REVIEW_INVALID")
    value = parse(raw)
    require(value["review_reference"] == "KRONOS-CA-TE03A-20261012",
            "THETA_TRIAL_CA_REVIEW_INVALID")
    review = OptionAuthorityReview(value["review_reference"], INSTRUMENT_REFERENCE,
        MARKET_REFERENCE, CURRENT_SHA256, "APPROVED", "APPROVED")
    return OwnerOptionAuthority(review=review)


def compose(paths):
    """Real-clock/nonqualification services; never creates charts or Questions."""
    paths.validate()
    workflow = ThetaWorkflow(ThetaStore(paths.root / "evidence"), inbox=paths.inbox,
                            outbox=paths.outbox, qualification_mode=False)
    publication = ThetaMethodologyPublication()
    now = workflow.now()
    method = publication.research_inputs(now)
    publication.assessment_policy(now)
    adapter = ThetaTargetAuthorityAdapter(reviewed_owner())
    targets = {subject: adapter.v3_inputs(subject, now) for subject in SUBJECTS}
    ownership = {"schema": "KRONOS-THETA-OPERATIONAL-ROOT-V1", "mode": paths.mode,
        "evidence": str(workflow.store.root), "inbox": str(paths.inbox), "outbox": str(paths.outbox),
        "candidate": str(REPOSITORY), "review_sha256": REVIEW_SHA256,
        "target_authority": adapter.owner.descriptor, "methodology": method["descriptor"]}
    # Foreign selections, rehearsal stores or qualification receipts may not be
    # adopted by placing them at the proposed genuine path. Clean or exact-owned.
    with directory(paths.root, create=True) as fd:
        names = set(os.listdir(fd))
        if OWNERSHIP in names:
            require(read_at(fd, OWNERSHIP) == encode(ownership), "THETA_TRIAL_FOREIGN_STORE")
        else:
            require(names <= {"support"}, "THETA_TRIAL_FOREIGN_STORE")
            write_at(fd, OWNERSHIP, encode(ownership))
        if "evidence" in names:
            with directory(workflow.store.root):
                pass
    producer = V3QuestionProducer(workflow, adapter, published_methodology=publication)
    app = ThetaSponsorWorkflow(producer, ThetaAssessmentEngine(producer.intake, publication))
    return app, {"mode": paths.mode, "qualification_mode": False,
                 "targets": targets, "methodology": method["descriptor"]}


def admit_originals(application, originals, *, sponsor_confirmed):
    """Six payloads only; fresh real-clock receipts, never copied state/metadata.

    Caller attestation is chart intent, not target/methodology approval. This
    explicit operation is for TE-09B; TE-09R exercises controlled images only.
    A retry reuses selected exact originals rather than manufacturing new times.
    """
    require(type(application) is ThetaSponsorWorkflow, "THETA_TRIAL_ORIGINAL_INVALID")
    require(sponsor_confirmed is True, "THETA_TRIAL_CHART_CONFIRMATION_REQUIRED")
    require(type(originals) is dict and set(originals) == set(CHART_ROLES), "THETA_TRIAL_ORIGINAL_INVALID")
    staged = {}
    for role in CHART_ROLES:
        item = originals[role]
        require(type(item) is dict and set(item) == {"payload", "media_type", "sha256"},
                "THETA_TRIAL_ORIGINAL_INVALID")
        raw = item["payload"]
        require(type(raw) is bytes and 0 < len(raw) <= MAX_CHART_BYTES
                and digest(raw) == item["sha256"]
                and item["media_type"] in {"image/png", "image/jpeg"}, "THETA_TRIAL_ORIGINAL_INVALID")
        signature = b"\x89PNG\r\n\x1a\n" if item["media_type"] == "image/png" else b"\xff\xd8\xff"
        require(raw.startswith(signature), "THETA_TRIAL_ORIGINAL_INVALID")
        try:
            image = ImageReader(BytesIO(raw)); width,height = image.getSize()
            require(0 < width*height <= 40_000_000, "THETA_TRIAL_ORIGINAL_INVALID")
            image.getRGBData()
        except Exception:
            raise ValueError("THETA_TRIAL_ORIGINAL_INVALID") from None
        staged[role] = item
    workflow = application.workflow
    workspace = workflow.chart_workspace()
    cards = {c["subject"]: c for c in workspace["cards"]}
    require(all(not cards[role]["chart"] or cards[role]["chart"]["sha256"] == item["sha256"]
                for role,item in staged.items()), "THETA_TRIAL_ORIGINAL_ADMISSION_CONFLICT")
    for role,item in staged.items():
        if cards[role]["chart"]:
            continue
        workflow.intake_chart(subject=role, label="Sponsor-confirmed TradingView composite — " + role,
            media_type=item["media_type"], payload=item["payload"],
            information_cutoff=workflow.now().isoformat(), cutoff_basis="INTAKE_RECEIPT_NOT_CHART_TIME")
    return workflow.chart_workspace()
