"""Application orchestration boundaries with fixed, on-demand public exports.

Importing a retained Intraday codec must not initialize unrelated Swing/PDF
modules. Exported objects and ordinary submodule loading retain their owners.
"""
from importlib import import_module

__all__ = ['AnalysisState', 'BrowserWorkspaceSnapshot', 'CompletedSwingAnalysis', 'EligiblePlanSnapshot', 'MarketPanel', 'OpportunitySnapshot', 'ProviderConnectionState', 'STEP31_V1_HANDOFF_SCHEMA_ID', 'Step31EligibilityHandoff', 'Step31EligibleInstrument', 'SwingAnalysisEvidenceSnapshot', 'SwingOpportunitiesApplication']

_EXPORTS = {'AnalysisState': ('kronos.application.swing_opportunities', 'AnalysisState'), 'BrowserWorkspaceSnapshot': ('kronos.application.swing_opportunities', 'BrowserWorkspaceSnapshot'), 'CompletedSwingAnalysis': ('kronos.application.swing_opportunities', 'CompletedSwingAnalysis'), 'EligiblePlanSnapshot': ('kronos.application.swing_opportunities', 'EligiblePlanSnapshot'), 'MarketPanel': ('kronos.application.swing_opportunities', 'MarketPanel'), 'OpportunitySnapshot': ('kronos.application.swing_opportunities', 'OpportunitySnapshot'), 'ProviderConnectionState': ('kronos.application.swing_opportunities', 'ProviderConnectionState'), 'SwingAnalysisEvidenceSnapshot': ('kronos.application.swing_opportunities', 'SwingAnalysisEvidenceSnapshot'), 'SwingOpportunitiesApplication': ('kronos.application.swing_opportunities', 'SwingOpportunitiesApplication'), 'STEP31_V1_HANDOFF_SCHEMA_ID': ('kronos.application.swing_v1_review', 'STEP31_V1_HANDOFF_SCHEMA_ID'), 'Step31EligibilityHandoff': ('kronos.application.swing_v1_review', 'Step31EligibilityHandoff'), 'Step31EligibleInstrument': ('kronos.application.swing_v1_review', 'Step31EligibleInstrument')}

def __getattr__(name):
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module, attribute = target
    value = getattr(import_module(module), attribute)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
