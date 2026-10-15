"""PLC-01 offline candidate composition; not deployment or trial migration.

Uses the retained product-owned stores/contracts. Construction reads only exact
static authority/methodology publications; no store, Provider or inbox operation.
"""
from pathlib import Path

from kronos.theta.assessment import ThetaAssessmentEngine
from kronos.theta.methodology import ThetaMethodologyPublication
from kronos.theta.operational import reviewed_owner
from kronos.theta.orchestration import ThetaSponsorWorkflow
from kronos.theta.producer_v3 import V3QuestionProducer
from kronos.theta.store import DEFAULT_ROOT, DEFAULT_INBOX, DEFAULT_OUTBOX, ThetaStore
from kronos.theta.target_authority import ThetaTargetAuthorityAdapter
from kronos.theta.workflow import ThetaWorkflow


def compose_theta_sponsor_workflow(*, root: Path = DEFAULT_ROOT,
                                 inbox: Path = DEFAULT_INBOX,
                                 outbox: Path = DEFAULT_OUTBOX):
    """Enroll source capability, not historical evidence or a second coordinator.

    Target eligibility is rechecked by the unchanged producer at commissioning;
    an expiry must not make shared startup depend on a forecast's availability.
    All store mutation stays in the existing explicit Sponsor operations.
    """
    workflow=ThetaWorkflow(ThetaStore(root),inbox=inbox,outbox=outbox,
                           qualification_mode=False)
    publication=ThetaMethodologyPublication()
    publication.research_inputs(workflow.now())
    publication.assessment_policy(workflow.now())
    producer=V3QuestionProducer(workflow,ThetaTargetAuthorityAdapter(reviewed_owner()),
                               published_methodology=publication)
    return ThetaSponsorWorkflow(producer,ThetaAssessmentEngine(producer.intake,publication))
