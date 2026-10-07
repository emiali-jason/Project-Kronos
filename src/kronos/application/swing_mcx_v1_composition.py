"""Canonical Swing MCX V1 composition, with no broker execution authority.

Construction is observational. Only an explicit, counted Browser POST reserves
a run. One historical owner survives run changes; current entry authority is a
separate slot. Provider capability and the existing shared monitoring hub remain
the sole authentication/stream owners.
"""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from threading import RLock
from uuid import uuid4
from zoneinfo import ZoneInfo

from kronos.application.swing_mcx_evidence import listed_v1_mcx_offers, retained_mcx_master_reader
from kronos.application.swing_mcx_integrated import SwingMcxIntegratedWorkflow
from kronos.application.swing_mcx_v1_operations import SwingMcxV1OperationalControl
from kronos.application.swing_trade_window import build_mcx_v1_trade_construction_evidence
from kronos.instrument.facts import publish_instrument_context
from kronos.provider.instrument_master_persistence import ProviderInstrumentSnapshotStore
from kronos.provider.contracts.instrument_master import ProviderInstrumentMasterError
from kronos.provider.kite.marketdata.kite_market_data_provider import KiteMarketDataProvider
from kronos.swing.run_publication import OperationToken
from kronos.swing.v1.mcx_broker_fill_evidence import LocalMcxBrokerFillEvidenceStore
from kronos.swing.v1.mcx_contract_profile import McxFamily
from kronos.swing.v1.mcx_contract_selection import (
    LocalMcxSponsorSelectionStore, McxSelectionRole,
    selected_mcx_instrument_before_acquisition,
)
from kronos.swing.v1.mcx_live_attestation import LocalMcxLiveFillAttestationStore
from kronos.swing.v1.mcx_prepared_plan_store import LocalMcxPreparedPlanStore
from kronos.swing.v1.mcx_step31_construction import (
    McxOneHourGeometry, select_owner_current_mcx_handoff,
)
from kronos.swing.v1.mcx_step31_prepared_handoff import _digest as bound_digest
from kronos.market.schedule import MarketDaySchedule, MarketWindow, TradingDayStatus
from kronos.swing.v1.mcx_trade_plan import LocalMcxTradePlanStore
from kronos.swing.v1.mcx_v1_advisory import LocalMcxV1AdvisoryStore
from kronos.swing.v1.native_trade_construction import _round_tick, _nearest_barrier
from kronos.swing.v1.models import V1Direction
from kronos.swing.v1.review_evidence_binding import canonical
from kronos.swing.v1.review_evidence_store import PreparedReadFence
from kronos.swing.run_identity import is_swing_analysis_run_id


def _hash(value):
    return sha256(canonical(value)).hexdigest()


_MASTER_LIST_FILE_LIMIT = 128 * 1024 * 1024
_MASTER_LIST_CHUNK = 1024 * 1024
_MASTER_LIST_HEADER_LIMIT = 256


def _retained_master_metadata(path):
    """Display-only metadata and exact bytes; never authenticated authority.

    Canonical DOMAIN-006 encoding begins with acquired_at. Read that bounded
    header and stream the file hash without constructing its entire record set.
    The explicit reservation still performs the unchanged full snapshot and
    authentication validation before publication admission.
    """
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("MCX_V1_MASTER_PATH_INVALID")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= _MASTER_LIST_FILE_LIMIT:
            raise ValueError("MCX_V1_MASTER_LIST_FILE_INVALID")
        stream = os.fdopen(descriptor, "rb")
    except BaseException:
        # Before a stream owns the descriptor, rejection must close it here.
        os.close(descriptor)
        raise
    with stream:
        first = stream.readline(_MASTER_LIST_HEADER_LIMIT)
        line = stream.readline(_MASTER_LIST_HEADER_LIMIT)
        try:
            header = json.loads(b"{" + line.rstrip().removesuffix(b",") + b"}")
            acquired = header["acquired_at"]
            moment = datetime.fromisoformat(acquired)
            expected = ('  "acquired_at": ' + json.dumps(acquired) + ',\n').encode("ascii")
        except (KeyError, TypeError, ValueError, UnicodeError) as error:
            raise ValueError("MCX_V1_MASTER_LIST_HEADER_INVALID") from error
        if (first != b"{\n" or line != expected or set(header) != {"acquired_at"}
                or moment.tzinfo is None or moment.utcoffset() is None):
            raise ValueError("MCX_V1_MASTER_LIST_HEADER_INVALID")
        digest = sha256(first + line)
        count = len(first) + len(line)
        for chunk in iter(lambda: stream.read(_MASTER_LIST_CHUNK), b""):
            count += len(chunk)
            if count > _MASTER_LIST_FILE_LIMIT:
                raise ValueError("MCX_V1_MASTER_LIST_FILE_INVALID")
            digest.update(chunk)
        after = os.fstat(stream.fileno())
        current = path.lstat()
        identity = lambda value: (value.st_dev, value.st_ino, value.st_size,
                                  value.st_mtime_ns, value.st_ctime_ns, value.st_mode)
        if count != before.st_size or identity(before) != identity(after) or identity(after) != identity(current):
            raise ValueError("MCX_V1_MASTER_CHANGED")
    return acquired, digest.hexdigest()


class SwingMcxV1Composition:
    """Installed before restoration, listener binding, READY or dispatch."""

    def __init__(self, server, *, master, provider, calendar, clock=None):
        if type(master) is not ProviderInstrumentSnapshotStore:
            raise ValueError("MCX_V1_COMPOSITION_MASTER_INVALID")
        self.server, self.master, self.calendar = server, master, calendar
        self.clock = clock or (lambda: datetime.now(UTC))
        self.publication = server.application._SwingOpportunitiesApplication__publication
        self.root = server.native_review.evidence_root / "mcx-v1"
        self._lock = RLock()
        self.selections = LocalMcxSponsorSelectionStore(self.root / "selections")
        self.prepared = LocalMcxPreparedPlanStore(self.root / "prepared")
        self.plans = LocalMcxTradePlanStore(self.root / "plans")
        self.control = SwingMcxV1OperationalControl(
            None, server.native_intake, server.native_review, self.plans,
            server.native_review._sponsor_decision_store,
            server.native_review._active_lifecycle,
            server.native_review._mcx_historical_contract_store,
            LocalMcxV1AdvisoryStore(self.root / "advisories"), master,
            server.application.mtf_fact_evidence_store(), provider, calendar,
            LocalMcxLiveFillAttestationStore(self.root / "live-attestations"),
            LocalMcxBrokerFillEvidenceStore(self.root / "broker-evidence"),
            server.application.authenticated_read_only_capability,
        )
        self.control.bind_maintenance_admission(server.maintenance_admission)
        from kronos.application.swing_mcx_observation import McxSelectedContractObservation
        self.observation = McxSelectedContractObservation(self.root / 'observations',
            hub=server.swing_monitoring_hub, admission=server.maintenance_admission,
            capability=server.application.authenticated_read_only_capability,
            calendar=calendar, selected=self.observation_selection,
            clock=lambda: self.clock())
        # Missing/stale reservation metadata withholds only NEW entry. It must
        # not disable the independently restored historical contract owner.
        self.restoration_error = None
        try:
            self.restore_current()
        except (OSError, ValueError, KeyError, TypeError):
            self.restoration_error = "MCX_V1_CURRENT_WORKFLOW_UNAVAILABLE"
        self.recover_historical_exits()

    def recover_historical_exits(self):
        """Finish only previously retained manual exit intents, before READY.

        No current run/capability is needed for a factual historical attestation.
        Incomplete evidence blocks startup; it is never silently replaced.
        """
        ticket = self.server.maintenance_admission.admit("SPONSOR_RESTORATION")
        if ticket is None:
            raise ValueError("MCX_V1_HISTORICAL_RECOVERY_FENCED")
        try:
            with ticket.activate():
                for position in self.control.lifecycle.snapshot().positions:
                    if (position.mcx_v1_contract_symbol is None
                            or position.mode.value != "LIVE"):
                        continue
                    path = self.control.live_attestations.root / (
                        position.position_id + ".exit-intent.json")
                    if path.exists() or path.is_symlink():
                        self.control.bound.recover_retained_live_exit(position.position_id,
                            self.control.live_attestations, self.control.broker_evidence)
        except Exception:
            self.control.close()
            raise
        finally:
            ticket.release()

    def publication_hash(self):
        if self.publication is None:
            return None
        return _hash(self.publication.status())

    def _descriptor_path(self, run):
        if not is_swing_analysis_run_id(run):
            raise ValueError("MCX_V1_RESERVATION_IDENTITY_INVALID")
        path = self.root / "reservations" / (run + ".json")
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError("MCX_V1_RESERVATION_PATH_INVALID")
        return path

    def _master_path(self, identity):
        path = self.master.path_for(provider="KITE",
            dataset_identity="KITE-INSTRUMENT-MASTER", snapshot_identity=identity)
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError("MCX_V1_MASTER_PATH_INVALID")
        return path

    def _retain_descriptor(self, value):
        path = self._descriptor_path(value["run"])
        payload = canonical({**value, "sha256": _hash(value)})
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / ("." + uuid4().hex + ".pending")
        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, path, follow_symlinks=False)
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            temporary.unlink(missing_ok=True)

    def _workflow(self, value):
        run = value["run"]
        moment = datetime.fromisoformat(value["observed_at"])
        if sha256(self._master_path(value["snapshot"]).read_bytes()).hexdigest() != value["master_sha256"]:
            raise ValueError("MCX_V1_MASTER_CHANGED")
        offers = listed_v1_mcx_offers(self.master, snapshot_identity=value["snapshot"],
            run_identity=run, observed_at=moment)
        if _hash({family.value: offer.offer_sha256 for family, offer in offers.items()}) != value["offers_sha256"]:
            raise ValueError("MCX_V1_OFFERS_CHANGED")
        token = OperationToken(value["generation"], run, value["predecessor"])
        workflow = SwingMcxIntegratedWorkflow(
            self.publication, self.selections, self.prepared, run,
            value["generation"], offers, "LOCAL_SPONSOR_EXPLICIT_POST", self.clock,
            reservation_token=token, predecessor=self.publication._load(value["predecessor"]),
            reserved_at=moment)
        workflow._current()
        return workflow

    def restore_current(self):
        """Read retained descriptor; never reserve or acquire at startup/GET."""
        if self.publication is None:
            self.restoration_error = "MCX_V1_PUBLICATION_OWNER_UNAVAILABLE"
            return
        attempt = self.publication.status()["latest_attempt"]
        run = attempt["run_id"]
        if not run:
            return
        path = self._descriptor_path(run)
        if not path.exists():
            return
        value = json.loads(path.read_bytes())
        digest = value.pop("sha256")
        if digest != _hash(value) or value["run"] != run:
            raise ValueError("MCX_V1_RESERVATION_CHANGED")
        workflow = self._workflow(value)
        self.control.bind_workflow(workflow, self.server.native_intake)
        self.server.mcx_slice3 = workflow

    def reserve(self, snapshot, master_sha256, publication_sha256):
        """Explicit Sponsor operation. Reject stale input before reservation."""
        with self._lock:
            if self.publication is None or self.server.native_intake is None:
                raise ValueError("MCX_V1_PUBLICATION_OWNER_UNAVAILABLE")
            now = self.clock()
            run = "SWING-RUN-" + uuid4().hex.upper()
            path = self._master_path(snapshot)
            if sha256(path.read_bytes()).hexdigest() != master_sha256:
                raise ValueError("MCX_V1_MASTER_CHANGED")
            try:
                offers = listed_v1_mcx_offers(self.master, snapshot_identity=snapshot,
                    run_identity=run, observed_at=now)
            except ProviderInstrumentMasterError as error:
                raise ValueError("MCX_V1_AUTHENTICATED_MASTER_UNAVAILABLE") from error
            if any(len(offer.selectable()) != 2 for offer in offers.values()):
                raise ValueError("MCX_V1_TWO_LISTED_CONTRACTS_UNAVAILABLE")
            control = self.publication.status()
            if _hash(control) != publication_sha256:
                raise ValueError("MCX_V1_PUBLICATION_CHANGED")
            if sha256(path.read_bytes()).hexdigest() != master_sha256:
                raise ValueError("MCX_V1_MASTER_CHANGED")
            # The publication owner performs the expected-control CAS inside
            # its existing flock. This also works with no current run.
            # Normal analysis claims its application work before publishing
            # RUNNING. Fence that interval under the same application lock.
            # Never hold this lock while binding the monitoring owner below.
            application = self.server.application
            with application._SwingOpportunitiesApplication__lock:
                work = application.analysis_work_status()
                execution = application.analysis_execution_status()
                if (work['state'] != 'IDLE' or work['owned_work_count']
                        or (execution is not None and
                            (execution.get('owned_workers', 0)
                             or execution.get('state') not in {'IDLE', 'SAME_PROCESS'}))):
                    raise ValueError('MCX_V1_ANALYSIS_OWNER_BUSY')
                token, predecessor = self.publication.admit(run, now,
                    expected_control=control, require_idle=True)
            try:
                value = dict(run=run, generation=token.generation,
                    predecessor=token.predecessor_manifest, observed_at=now.isoformat(),
                    snapshot=snapshot, master_sha256=master_sha256,
                    offers_sha256=_hash({family.value: offer.offer_sha256
                                       for family, offer in offers.items()}))
                self._retain_descriptor(value)
                workflow = SwingMcxIntegratedWorkflow(self.publication,
                    self.selections, self.prepared, run, token.generation,
                    offers, "LOCAL_SPONSOR_EXPLICIT_POST", self.clock,
                    reservation_token=token, predecessor=predecessor, reserved_at=now)
                self.control.bind_workflow(workflow, self.server.native_intake)
                self.server.mcx_slice3 = workflow
                return workflow
            except Exception:
                self.publication.fail(token, self.clock(), "SWING_ANALYSIS_FAILED")
                raise

    def observation_selection(self, run, family, selection_sha256, publication_sha256):
        """Exact retained choice/current publication fence; no acquisition/write."""
        workflow = self.control.workflow
        if (workflow is None or run != workflow.run_identity
                or type(family) is not McxFamily):
            raise ValueError('MCX_OBSERVATION_RUN_STALE')
        workflow._current()
        baseline = self.publication.status()
        if (_hash(baseline) != publication_sha256
                or baseline['latest_attempt']['state'] != 'SUCCEEDED'
                or baseline['latest_attempt']['run_id'] != run
                or baseline['admission_generation'] != workflow.generation):
            raise ValueError('MCX_OBSERVATION_PUBLICATION_CHANGED')
        selected = workflow.selections.load(run, family)
        if selected.integrity_sha256 != selection_sha256:
            raise ValueError('MCX_OBSERVATION_SELECTION_CHANGED')
        match = workflow.retained_selected_contract(family, self.master, acquired_at=self.clock())
        if (self.control.workflow is not workflow or self.publication.status() != baseline
                or workflow.selections.load(run, family) != selected):
            raise ValueError('MCX_OBSERVATION_SELECTION_CHANGED')
        return dict(run=run, generation=workflow.generation, family=family.value,
            selection_sha256=selected.integrity_sha256,
            instrument=match.normalized_contract, publication=baseline['current_manifest'],
            historical_master_identity=match.snapshot_identity,
            historical_master_authority='IDENTITY_ONLY_NOT_CURRENT_MAPPING')

    def prepare_plan(self, run, family, expected_handoff):
        self.control._active_capability()
        workflow = self.control.workflow
        if workflow is None or run != workflow.run_identity:
            raise ValueError("MCX_V1_RUN_STALE")
        now = self.clock()
        match = workflow.retained_selected_contract(family, self.master, acquired_at=now)
        derivative = match.normalized_contract
        owner = select_owner_current_mcx_handoff(self.server.native_intake,
            family, derivative, prepared_at=now)
        if owner.prepared.bound.run_identity != workflow.run_identity:
            raise ValueError('MCX_V1_RUN_STALE')
        if bound_digest(asdict(owner.prepared.bound)) != expected_handoff:
            raise ValueError("MCX_V1_HANDOFF_CHANGED")
        intake = self.server.native_intake
        with intake._validated_response() as (response, reads):
            _, facts, _ = intake._context(_response=response)
            requirement = intake._requirements("MCX", (family.value,), _response=response)[0]
            promotion = intake.v2_for(run, family.value, _response=response)
            if (promotion is None or promotion.value["integrity_sha256"]
                    != owner.prepared.bound.promotion_integrity_sha256
                    or requirement.requirement_sha256 != owner.prepared.bound.requirement_sha256):
                raise ValueError("MCX_V1_REVIEW_CHANGED")
            evidence = build_mcx_v1_trade_construction_evidence(requirement, facts, promotion)
            geometry_fence = PreparedReadFence(tuple(reads.items()))
        # Reuse governed Step-31 evidence and DOMAIN-001 tick rounding. This
        # produces price advice only; it never creates an NSE eligibility
        # handoff, Risk permission, ECPC or a P32-002 execution outcome.
        context = publish_instrument_context(family.value, "MCX_COMMODITY", derivative)
        direction = requirement.thesis.direction
        candle = evidence.qualification_candle
        structural = (evidence.governing_structural_low if direction is V1Direction.LONG
                      else evidence.governing_structural_high)
        target = (evidence.prior_directional_swing_high if direction is V1Direction.LONG
                  else evidence.prior_directional_swing_low)
        if candle is None or structural is None or target is None:
            raise ValueError("MCX_V1_GEOMETRY_UNAVAILABLE")
        entry = _round_tick(candle.high if direction is V1Direction.LONG else candle.low,
                            context, up=direction is V1Direction.LONG)
        stop = _round_tick(structural.price, context, up=direction is V1Direction.SHORT)
        target_price = _round_tick(target.price, context, up=direction is V1Direction.SHORT)
        barrier = _nearest_barrier(evidence.material_barriers, entry, target_price, direction)
        if barrier is not None:
            target_price = _round_tick(barrier.price, context, up=direction is V1Direction.SHORT)
        bound = owner.prepared.bound
        geometry = McxOneHourGeometry(entry, stop, target_price,
            bound.completed_one_hour_sha256, bound.completed_one_hour_boundary)
        schedule = self.calendar.schedule("MCX", now.astimezone(
            ZoneInfo("Asia/Kolkata")).date(), observed_at=now)
        if schedule is None:
            raise ValueError("MCX_V1_SESSION_UNAVAILABLE")
        schedule = MarketDaySchedule("MCX", schedule.trading_date,
            schedule.session_identity, schedule.timezone, TradingDayStatus.TRADING,
            tuple(MarketWindow(window.window_open, window.window_close)
                  for window in schedule.windows),
            schedule.calendar_identity, schedule.calendar_version)
        # An identical explicit replay reuses its retained immutable plan.
        # No evidence rebind, created-at rewrite or duplicate position follows.
        existing_paths = sorted((self.plans.root / run / family.value).glob('*.json'))
        if len(existing_paths) > 32:
            raise ValueError("MCX_V1_PLAN_PROJECTION_LIMIT")
        for path in existing_paths:
            previous = self.plans.load(path)
            if (previous.receipt_integrity_sha256 == owner.prepared.bound.receipt_integrity_sha256
                    and previous.promotion_integrity_sha256 == owner.prepared.bound.promotion_integrity_sha256
                    and previous.selection_sha256 == workflow.selections.load(run, family).integrity_sha256
                    and previous.expiry_session_identity == schedule.session_id
                    and now < previous.entry_eligibility_boundary):
                self.control._current_plan_owner(previous)
                with owner.final_fence():
                    geometry_fence.check()
                    workflow._current()
                return previous, path
        with owner.final_fence():
            # Only byte rechecks under WO-05 -> WO-07. Full validation and
            # geometry composition above occur before acquiring these locks.
            workflow._current()
        return workflow.construct_v1_advisory_plan(self.server.native_intake,
            family, derivative, geometry, self.master, schedule, self.plans,
            opportunity=requirement.thesis.opportunity_identity, created_at=now,
            geometry_fence=geometry_fence)

    def projection(self):
        """No recovery, reservations, writes, subscriptions or market I/O."""
        workflow = self.control.workflow
        current, error = False, self.restoration_error
        if workflow is not None:
            try:
                workflow._current()
                current = True
            except ValueError:
                error = "MCX_V1_RUN_STALE"
        reserved = (current and self.publication is not None and
                    self.publication.status()['latest_attempt']['state'] == 'RUNNING')
        plans = []
        preparations = []
        observation_targets = []
        if current and not reserved:
            now = self.clock()
            try:
                control = self.publication.status()
                attempt = control['latest_attempt']
                # _current() and the reserved check ran earlier. Bind the
                # projection baseline itself to the workflow that passed them;
                # otherwise a newer run admitted in between could be mistaken
                # for a stable baseline while this older run is projected.
                if (control['admission_generation'] != workflow.generation
                        or attempt['run_id'] != workflow.run_identity
                        or attempt['state'] != 'SUCCEEDED'):
                    raise ValueError('MCX_V1_RUN_STALE')

                def current_workflow_control(value):
                    current_attempt = value['latest_attempt']
                    return (value['admission_generation'] == workflow.generation
                            and current_attempt['run_id'] == workflow.run_identity
                            and current_attempt['state'] == 'SUCCEEDED')

                # One retained Review context and one full parse per selected
                # master, rather than reconstructing both for every family/plan.
                with ExitStack() as stack:
                    response = stack.enter_context(self.server.native_intake.page_response())
                    readers = {}
                    selected_records = {}
                    for family in McxFamily:
                        owner = selected = instrument = None
                        try:
                            selected = workflow.selections.load(workflow.run_identity, family)
                            selected_records[family] = selected
                            offer = workflow.offers[family]
                            fact = (offer.near if selected.role is McxSelectionRole.NEAR
                                    else offer.next_eligible)
                            if (fact is None or not fact.provider_snapshot_identity
                                    or not fact.provider_record_identity):
                                raise ValueError("MCX_RETAINED_CONTRACT_REFERENCE_UNAVAILABLE")
                            instrument = selected_mcx_instrument_before_acquisition(
                                workflow.selections, offer, (fact.instrument,), acquired_at=now)
                            identity = fact.provider_snapshot_identity
                            if identity not in readers:
                                readers[identity] = None
                                readers[identity] = stack.enter_context(retained_mcx_master_reader(
                                    self.master, snapshot_identity=identity, observed_at=now))
                            if readers[identity] is None:
                                raise ValueError("MCX_RETAINED_MASTER_UNAVAILABLE")
                            readers[identity](fact.provider_record_identity, family, instrument)
                            observation_targets.append((family.value,
                                instrument.trading_symbol, instrument.expiry.isoformat(),
                                selected.integrity_sha256))
                            owner = select_owner_current_mcx_handoff(self.server.native_intake,
                                family, instrument, prepared_at=now, _response=response)
                            if owner.prepared.bound.run_identity != workflow.run_identity:
                                raise ValueError("MCX_V1_RUN_STALE")
                            preparations.append((family.value, bound_digest(asdict(owner.prepared.bound))))
                        except (OSError, ValueError):
                            owner = None
                        directory = self.plans.root / workflow.run_identity / family.value
                        for path in sorted(directory.glob("*.json")):
                            if len(plans) >= 32:
                                raise ValueError("MCX_V1_PLAN_PROJECTION_LIMIT")
                            plan = self.plans.load(path)
                            eligible = False
                            if owner is not None:
                                try:
                                    plan_owner = select_owner_current_mcx_handoff(
                                        self.server.native_intake, family, instrument,
                                        prepared_at=plan.created_at, _response=response)
                                    workflow._validate_v1_plan_owner(
                                        family, instrument, plan, self.plans, selected, plan_owner)
                                    eligible = True
                                except (OSError, ValueError):
                                    pass
                            plans.append((plan, eligible))
                    current_control = self.publication.status()
                    if (self.control.workflow is not workflow
                            or not current_workflow_control(current_control)
                            or current_control != control
                            or any(workflow.selections.load(workflow.run_identity, family) != selected
                                   for family, selected in selected_records.items())):
                        raise ValueError("MCX_V1_RUN_STALE")
                # Recheck after the response/master exit fences as well.
                current_control = self.publication.status()
                if (self.control.workflow is not workflow
                        or not current_workflow_control(current_control)
                        or current_control != control
                        or any(workflow.selections.load(workflow.run_identity, family) != selected
                               for family, selected in selected_records.items())):
                    raise ValueError("MCX_V1_RUN_STALE")
            except (OSError, ValueError):
                # A failed final fence cannot leave actionable-looking results.
                preparations.clear()
                observation_targets.clear()
                plans = [(plan, False) for plan, _ in plans]
                error = "MCX_V1_PROJECTION_UNAVAILABLE"
        return dict(run=None if workflow is None else workflow.run_identity,
            current=current, reserved=reserved, error=error, publication_sha256=self.publication_hash(),
            plans=tuple(plans), preparations=tuple(preparations), positions=tuple((position,
                self.control.historical.load(position.position_id)) for position in
                self.control.lifecycle.snapshot().positions
                if position.mcx_v1_contract_symbol is not None),
            observation_targets=tuple(observation_targets),
            capability_active=getattr(self.server.application.authenticated_read_only_capability(),
                                      "active", False) is True)

    def retained_snapshots(self):
        """Unvalidated file listing; reservation owns full snapshot validation."""
        directory = self.master._root / "KITE" / "KITE-INSTRUMENT-MASTER"
        if any(parent.is_symlink() for parent in (directory, *directory.parents)):
            raise ValueError("MCX_V1_MASTER_PATH_INVALID")
        paths = []
        try:
            for path in directory.iterdir():
                if path.suffix != ".json":
                    continue
                if len(paths) >= 16:
                    raise ValueError("MCX_V1_MASTER_LIST_LIMIT")
                paths.append(path)
        except FileNotFoundError:
            return ()
        results = []
        for path in sorted(paths):
            acquired_at, digest = _retained_master_metadata(path)
            results.append((path.stem, acquired_at, digest))
        return tuple(results)


def install_canonical_mcx_v1(server, *, master, calendar):
    """Use the existing Swing capability; no Connect or acquisition at install."""
    return SwingMcxV1Composition(server, master=master, calendar=calendar,
        provider=lambda: KiteMarketDataProvider(
            server.application.authenticated_read_only_capability()))
