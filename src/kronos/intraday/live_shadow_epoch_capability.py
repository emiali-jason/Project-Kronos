"""Deterministic semantic capability for the WO-06H acceptance epoch boundary."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import ast
import importlib

from kronos.intraday.population_measurement import canonical
from kronos.intraday.runtime_identity import LoadedCapability


CAPABILITY_IDENTITY = "WO_06H_ACCEPTANCE_EPOCH"
CAPABILITY_VERSION = "1.2.0"
DIGEST_POLICY = "KRONOS-WO06H-ACCEPTANCE-EPOCH-SEMANTIC-AST/1.0.0"
SEMANTICALLY_PROTECTED = "SEMANTICALLY_PROTECTED"

# Explicit policy allowlist. The prior 36 runtime code objects are represented by
# their owned source definitions. The two additive compatibility functions protect
# the exact, non-general 1.1.0 -> 1.2.0 collateral transition.
PROTECTED_CALLABLES = (
    ("kronos.application.intraday_shadow_epochs", "repository_gate"),
    ("kronos.application.intraday_shadow_epochs", "restore_epoch"),
    ("kronos.application.intraday_shadow_epochs", "epoch_status"),
    ("kronos.application.intraday_shadow_epochs", "commission"),
    ("kronos.intraday.live_shadow", "validate_body"),
    ("kronos.application.intraday_live_shadow", "IntradayLiveShadowService.__init__"),
    ("kronos.application.intraday_live_shadow", "IntradayLiveShadowService._active"),
    ("kronos.application.intraday_live_shadow", "IntradayLiveShadowService._epoch_current"),
    ("kronos.application.intraday_live_shadow", "IntradayLiveShadowService.status"),
    ("kronos.application.intraday_live_shadow", "IntradayLiveShadowService._restore_acceptance"),
    ("kronos.intraday.live_shadow_epochs", "document"),
    ("kronos.intraday.live_shadow_epochs", "validate"),
    ("kronos.intraday.live_shadow_epochs", "capabilities"),
    ("kronos.intraday.live_shadow_epochs", "compatible"),
    ("kronos.intraday.live_shadow_epochs", "epoch_document"),
    ("kronos.intraday.live_shadow_epochs", "EpochStore.__init__"),
    ("kronos.intraday.live_shadow_epochs", "EpochStore._directory"),
    ("kronos.intraday.live_shadow_epochs", "EpochStore._read"),
    ("kronos.intraday.live_shadow_epochs", "EpochStore.load"),
    ("kronos.intraday.live_shadow_epochs", "EpochStore.retain"),
    ("kronos.intraday.live_shadow_epochs", "EpochStore.transaction"),
    ("kronos.intraday.live_shadow_epochs", "EpochStore.pointer"),
    ("kronos.intraday.live_shadow_epochs", "EpochStore.anchor_legacy"),
    ("kronos.intraday.live_shadow_epochs", "EpochStore.managed"),
    ("kronos.intraday.live_shadow_epochs", "EpochStore.advance"),
    ("kronos.intraday.live_shadow_epochs", "EpochStore.legacy"),
    ("kronos.intraday.live_shadow_epochs", "EpochStore.bound"),
    ("kronos.intraday.live_shadow_epochs", "EpochStore.chain"),
    ("kronos.intraday.live_shadow_epochs", "EpochStore.equivalence"),
    ("kronos.intraday.live_shadow_epochs", "EpochView.__init__"),
    ("kronos.intraday.live_shadow_epochs", "EpochView._epoch"),
    ("kronos.intraday.live_shadow_epochs", "EpochView.all"),
    ("kronos.intraday.live_shadow_epochs", "EpochView.load"),
    ("kronos.intraday.live_shadow_epochs", "EpochView.retain"),
    ("kronos.intraday.live_shadow_transition", "capability_identity"),
    ("kronos.intraday.live_shadow_transition", "capability_delta"),
    ("kronos.intraday.live_shadow_transition", "validate_bridge"),
    ("kronos.intraday.live_shadow_transition", "validate_equivalence"),
)


class _WithoutDocstrings(ast.NodeTransformer):
    def _strip(self, node):
        node = self.generic_visit(node)
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            node.body = node.body[1:]
        return node

    visit_FunctionDef = _strip
    visit_AsyncFunctionDef = _strip
    visit_ClassDef = _strip


def _source(module_name, sources):
    if sources is not None:
        value = sources[module_name]
        if type(value) is not str:
            raise ValueError("SHADOW_EPOCH_SEMANTIC_SOURCE_INVALID")
        return value
    module = importlib.import_module(module_name)
    loader = module.__spec__.loader
    value = None if loader is None or not hasattr(loader, "get_source") else loader.get_source(module_name)
    if type(value) is not str:
        raise ValueError("SHADOW_EPOCH_SEMANTIC_SOURCE_UNAVAILABLE")
    return value


def _definition(source, qualified_name):
    body = ast.parse(source).body
    parts = qualified_name.split(".")
    selected = None
    for part in parts:
        matches = [node for node in body
                   if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                   and node.name == part]
        if len(matches) != 1:
            raise ValueError("SHADOW_EPOCH_SEMANTIC_CALLABLE_UNAVAILABLE")
        selected = matches[0]
        body = selected.body
    selected = _WithoutDocstrings().visit(deepcopy(selected))
    return ast.dump(selected, annotate_fields=True, include_attributes=False)


def policy_declarations():
    from kronos.intraday import live_shadow_epochs, live_shadow_transition
    return {
        "capability": {"identity": CAPABILITY_IDENTITY, "version": CAPABILITY_VERSION},
        "digest_policy": DIGEST_POLICY,
        "epoch_policy": live_shadow_epochs.POLICY,
        "methodology": live_shadow_epochs.METHOD,
        "narrow_cpr": live_shadow_epochs.CPR,
        "classifications": [live_shadow_epochs.MATERIAL, live_shadow_epochs.COLLATERAL],
        "document_identity_pattern": live_shadow_epochs.ID.pattern,
        "fields": {key: sorted(value) for key, value in live_shadow_epochs.FIELDS.items()},
        "collateral_diagnosis_fields": sorted(live_shadow_epochs.COLLATERAL_DIAGNOSIS_FIELDS),
        "transition_invariants": list(live_shadow_transition.INVARIANT_SEMANTICS),
    }


def semantic_payload(calculation, *, sources=None, declarations=None):
    if (type(calculation) is not LoadedCapability
            or calculation.identity != "WO_06H_LIVE_SHADOW"):
        raise ValueError("SHADOW_EPOCH_CALCULATION_CAPABILITY_INVALID")
    declarations = policy_declarations() if declarations is None else deepcopy(declarations)
    rows = []
    source_cache = {}
    for module_name, qualified_name in PROTECTED_CALLABLES:
        if module_name not in source_cache:
            source_cache[module_name] = _source(module_name, sources)
        source = source_cache[module_name]
        rows.append({"module": module_name, "callable": qualified_name,
                     "classification": SEMANTICALLY_PROTECTED,
                     "canonical_ast": _definition(source, qualified_name)})
    return canonical({"declarations": declarations,
                      "calculation_capability": {
                          "identity": calculation.identity,
                          "version": calculation.version,
                          "implementation_digest": calculation.implementation_digest,
                      },
                      "protected_callables": rows})


def capability(calculation, *, sources=None, declarations=None):
    payload = semantic_payload(calculation, sources=sources, declarations=declarations)
    return LoadedCapability(CAPABILITY_IDENTITY, CAPABILITY_VERSION, sha256(payload).hexdigest())


def protected_source_identities(*, sources=None):
    modules = sorted({module for module, _ in PROTECTED_CALLABLES})
    return [{"module": module, "sha256": sha256(_source(module, sources).encode()).hexdigest()}
            for module in modules]
