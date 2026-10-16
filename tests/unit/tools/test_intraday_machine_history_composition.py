"""Execute the exact canonical composition assignment with inert real stores."""
import ast
from pathlib import Path
from types import SimpleNamespace
from kronos.application.intraday_machine_history import IntradayMachineHistory
from kronos.intraday.wo08_assessment_store import Wo08AssessmentStore
from kronos.intraday.probables_v2_persistence import ProbablesV2Store
from kronos.intraday.wo09_persistence import Wo09Store
from tests.unit.application.test_intraday_machine_history import inventory


def test_canonical_assignment_injects_same_stores_and_bound_method_without_reads(tmp_path):
    tree=ast.parse((Path(__file__).resolve().parents[3]/'tools/kronos_browser.py').read_text())
    main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    assignment=next(n for n in ast.walk(main) if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='intraday_machine_history' for t in n.targets))
    runtime=SimpleNamespace(wo08_store=Wo08AssessmentStore(tmp_path),
        probables_v2_store=ProbablesV2Store(tmp_path),wo09_store=Wo09Store(tmp_path))
    class Control:
        def analysis_history_document(self):raise AssertionError('constructor read')
    control=Control();env=dict(IntradayMachineHistory=IntradayMachineHistory,
        intraday_runtime=runtime,intraday_probables_v2_control=control)
    before=inventory(tmp_path)
    exec(compile(ast.Module(body=[assignment],type_ignores=[]),'<exact-canonical-assignment>','exec'),env)
    obj=env['intraday_machine_history']
    assert obj.assessments is runtime.wo08_store and obj.probables is runtime.probables_v2_store
    assert obj.readiness is runtime.wo09_store
    assert obj.recent_attempts.__self__ is control
    assert obj.recent_attempts.__func__ is Control.analysis_history_document
    assert inventory(tmp_path)==before
    route_call=next(n for n in ast.walk(main) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
        and n.func.id=='IntradayBrowserRoutes')
    assert next(k.value.id for k in route_call.keywords if k.arg=='machine_history')=='intraday_machine_history'
    assert all(not isinstance(n,ast.Attribute) or n.attr not in {'load_run','load_readiness','restore_latest'}
               for n in ast.walk(assignment))
