"""Exact MCX Native bindings; synthetic approved source, no market operation."""
import pytest

from kronos.intraday.wo10_futures_contract import digest
from kronos.intraday.wo10_native_adapter import adapt_native
from kronos.intraday.wo10_construction import construct_plan
from tests.unit.intraday.test_wo10_native_composition import native, retain
from tests.unit.intraday.test_wo10_futures import intake, NOW


@pytest.mark.parametrize("family", ["CRUDE", "COPPER", "GOLDM", "SILVERM"])
@pytest.mark.parametrize("case", ["valid", "wrong_contract", "wrong_roll"])
def test_exact_native_mcx_contract_and_roll(tmp_path, family, case):
    app,_,v,source=native(tmp_path/"source")
    subject="MCX-SUBJECT-"+family
    contract="EXACT-TEST-CONTRACT-"+family
    roll="EXACT-TEST-ROLL-"+family
    store,r,h=intake(tmp_path/"mcx",subject=subject,market_family="MCX",
        exact_mcx_contract_identity=contract,exact_mcx_roll_lineage=roll,session_identity="MCX-2026-09-11")
    app.wo09=store
    for target in (v,source):
        target.update(subject=subject,session=h.session_identity,exact_contract=contract,roll_lineage=roll,
                      machine_integrity=h.machine_evidence_integrity)
    v["instrument_identity"]=contract
    for candle in source["candles"].values():candle.update(subject=subject,session=h.session_identity)
    for reference in v["roles"].values():reference["candle_integrity"]=digest(source["candles"][reference["candle_identity"]])
    v["sources"][source["identity"]]=digest(source)
    selected=retain(app,v)
    if case!="valid":
        _,_,h=intake(tmp_path/"different",subject=subject,market_family="MCX",
            exact_mcx_contract_identity="WRONG-CONTRACT" if case=="wrong_contract" else contract,
            exact_mcx_roll_lineage="WRONG-ROLL" if case=="wrong_roll" else roll,session_identity="MCX-2026-09-11")
        with pytest.raises(ValueError,match="SOURCE_(EXACT_CONTRACT|ROLL_LINEAGE)_MISMATCH"):
            app.structural_loader.load(h,now=NOW)
    else:
        assert app.structural_loader.load(h,now=NOW)==selected
        adapter,evidence,population=adapt_native(selected,h,r,store.load_pointer(subject),now=NOW)
        plan=construct_plan(adapter,evidence,population,now=NOW)
        assert plan.data["state"]=="AVAILABLE"
        assert plan.data["wo09"]["exact_mcx_contract_identity"]==contract
        assert plan.data["wo09"]["exact_mcx_roll_lineage"]==roll
    assert app.store.records("WO10_FUTURES_MARKET_SNAPSHOT_V1")==()
