"""WO-05C declarations derived from composed, loaded Intraday implementations."""
from hashlib import sha256
import marshal
import os

from kronos.application import intraday_discovery_operation as operation_module
from kronos.intraday import analysis_time, operation_accounting
from kronos.intraday.operation_accounting_persistence import DiscoveryOperationAccountingStore
from kronos.intraday.runtime_identity import LoadedCapability, create_runtime_manifest


def _capability(identity, version, *functions):
    code = b"".join(marshal.dumps(function.__code__) for function in functions)
    return LoadedCapability(identity, version, sha256(code).hexdigest())


def compose_runtime_manifest(startup, configuration, operation, control):
    if startup is None or startup.process_id != os.getpid():
        return None
    capabilities = []
    if type(operation) is operation_module.IntradayDiscoveryOperationService:
        capabilities.append(_capability("INTRADAY_DISCOVERY_OPERATION", operation_module.DISCOVERY_OPERATION_SERVICE_VERSION, operation.execute))
        names = operation.execute.__code__.co_names
        if ("admit_analysis_time" in names and operation_module.admit_analysis_time is analysis_time.admit_analysis_time):
            capabilities.append(_capability("WO_05A_TRUSTED_TIME_ADMISSION", "1.0.0", operation.execute, analysis_time.admit_analysis_time))
        if ("ProviderRequestCounter" in names and operation_module.ProviderRequestCounter is operation_accounting.ProviderRequestCounter
            and type(operation.accounting_store) is DiscoveryOperationAccountingStore):
            capabilities.append(_capability("WO_05B_OPERATION_ACCOUNTING", "1.0.0", operation.execute,
                operation_accounting.ProviderRequestCounter.invoke, operation._retain_accounting))
    # The caller is a constructed current control, not a source-file inventory.
    from kronos.browser.intraday_probables_v2_control import (
        IntradayProbablesV2OperationalControl, INTRADAY_PROBABLES_V2_CONTROL_VERSION,
    )
    if type(control) is IntradayProbablesV2OperationalControl and control.operation_service is operation:
        capabilities.append(_capability("INTRADAY_V2_OPERATIONAL_CONTROL", INTRADAY_PROBABLES_V2_CONTROL_VERSION, control.execute_document, control.status_document))
    from kronos.application.intraday_live_shadow import IntradayLiveShadowService
    from kronos.intraday import live_shadow_features, live_shadow_quote
    from kronos.intraday.technical_context_research import decimal_policy
    shadow = getattr(operation, "live_shadow", None)
    if type(shadow) is IntradayLiveShadowService:
        calculation = _capability("WO_06H_LIVE_SHADOW", "1.0.0", shadow.capture_published,
            shadow._capture, shadow.complete_eod, shadow.accept_runtime, live_shadow_features.classify,
            live_shadow_features.snapshot, live_shadow_quote.capture, live_shadow_quote.native_context,
            live_shadow_features._decision, live_shadow_features._validate_cpr, live_shadow_features._evaluate_member,
            live_shadow_features.sma.__wrapped__, live_shadow_features.vwap.__wrapped__,
            live_shadow_features.measure.__wrapped__, decimal_policy)
        capabilities.append(calculation)
    if type(shadow) is IntradayLiveShadowService:
        from kronos.application.intraday_shadow_epochs import epoch_capability
        capabilities.append(epoch_capability(calculation))
    return create_runtime_manifest(startup, configuration, capabilities)
