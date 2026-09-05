"""Explicit clipboard payload validation and unchanged governed chart persistence."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess

import pytest
from PIL import Image, ImageDraw

from kronos.application.intraday_review_v2 import IntradayReviewV2Application
from kronos.browser.intraday_views import _review_v2_chart_script
from kronos.browser.product_routes import BrowserPostRequest
from kronos.intraday.review_v2 import REVIEW_V2_CHART_ROUTE
from kronos.intraday.review_v2_persistence import IntradayReviewV2Store
from kronos.intraday.review_pdf import DEFAULT_QUESTION_OUTBOX, DEFAULT_ANSWER_INBOX
from tests.unit.browser.test_intraday_review_workflow import _routes, _fingerprints
from tests.unit.browser.test_intraday_review_v2_control import _payload
from tests.unit.browser.test_product_route_isolation import _snapshot
from tests.unit.intraday.test_review_v2 import _retain_later_current_run


def _image(fmt="PNG", size=(640, 400), color="navy"):
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    for i, label in enumerate(("COMEX 1D", "COMEX 4H", "COMEX 15M", "COMEX 5M",
                               "MCX 1D", "MCX 4H", "MCX 15M", "MCX 5M")):
        x, y = (i % 4) * size[0] // 4, (i // 4) * size[1] // 2
        draw.rectangle((x, y, x + size[0] // 4 - 1, y + size[1] // 2 - 1), outline="white")
        draw.text((x + 10, y + 10), label, fill="white")
    output = BytesIO(); image.save(output, format=fmt)
    return output.getvalue()


def _send(routes, cycle, data, mime="image/png", query=None):
    response = routes.handle_post(BrowserPostRequest(REVIEW_V2_CHART_ROUTE,
        {"cycle": [cycle]} if query is None else query, mime, data), _snapshot)
    return response, json.loads(response.body)


@pytest.mark.parametrize("fmt,mime", [("PNG", "image/png"), ("JPEG", "image/jpeg")])
def test_original_composite_common_intake_replacement_restoration_and_question_transport(tmp_path, fmt, mime):
    run, app, control, routes = _routes(tmp_path)
    control.execute_document(_payload(run)); cycle = app.snapshot().candidates[0].cycle_identity
    data = _image(fmt, (4096, 2048)); before_cycles = _fingerprints(app.review_store.root / "cycles")
    response, result = _send(routes, cycle, data, mime)
    assert response.status == 200 and result["outcome"] == "CHART_RECEIVED"
    first = app.review_store.load_current_chart(cycle)
    chart = app.review_store.load_chart(first.chart_revision_identity)
    assert chart.payload_sha256 == hashlib.sha256(data).hexdigest()
    assert chart.media_type == mime and chart.revision_ordinal == 1
    assert app.review_store.load_chart_bytes(chart) == data
    _send(routes, cycle, data, mime)
    assert app.review_store.load_current_chart(cycle) == first
    data2 = _image(fmt, (4096, 2048), "darkgreen")
    _send(routes, cycle, data2, mime)
    second = app.review_store.load_current_chart(cycle)
    assert second.revision_ordinal == 2 and second.chart_revision_identity != first.chart_revision_identity
    assert app.review_store.load_chart_bytes(chart) == data
    assert _fingerprints(app.review_store.root / "cycles") == before_cycles
    restored = IntradayReviewV2Application(probables_store=app.probables_store,
        review_store=IntradayReviewV2Store(app.review_store.root))
    candidate = restored.snapshot().candidates[0]
    assert candidate.chart_revision_identity == second.chart_revision_identity
    assert candidate.chart_state == "CHART_READY"
    assert restored.review_store.load_current_chart(cycle) == second
    batch = app.create_combined_question_transport()
    assert batch is not None
    assert list((tmp_path / "v2" / "questions").glob("*.pdf"))
    assert app.review_store.load_chart_bytes(app.review_store.load_chart(second.chart_revision_identity)) == data2
    assert DEFAULT_QUESTION_OUTBOX == Path("/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/Intraday/KRONOS QUESTIONS")
    assert DEFAULT_ANSWER_INBOX == Path("/Users/imranali/Documents/Project-KRONOS/KRONOS REVIEW PACK/Intraday/CHATGPT ANSWERS")


def test_chart_browser_failures_are_bounded_and_preserve_current_pointer(tmp_path, monkeypatch):
    run, app, control, routes = _routes(tmp_path)
    control.execute_document(_payload(run)); cycle = app.snapshot().candidates[0].cycle_identity
    _send(routes, cycle, _image()); prior = app.review_store.load_current_chart(cycle)
    for query, mime, data, reason in [
        ({"cycle": [cycle, cycle]}, "image/png", _image(), "INVALID_CANDIDATE_BINDING"),
        ({"cycle": ["FOREIGN"]}, "image/png", _image(), "STALE_REVIEW_CYCLE"),
        ({"cycle": [cycle]}, "image/gif", b"GIF", "UNSUPPORTED_IMAGE_TYPE"),
        ({"cycle": [cycle]}, "image/png", b"invalid", "INVALID_CHART_IMAGE"),
        ({"cycle": [cycle]}, "image/png", b"x" * (25 * 1024 * 1024 + 1), "IMAGE_TOO_LARGE"),
    ]:
        response, result = _send(routes, cycle, data, mime, query)
        assert response.status >= 400 and result["reason"] == reason
        assert app.review_store.load_current_chart(cycle) == prior
    def fail(*args, **kwargs):
        raise OSError("SECRET /private/sensitive/path")
    with monkeypatch.context() as patch:
        patch.setattr(app.review_store, "retain_chart", fail)
        response, result = _send(routes, cycle, _image(color="red"))
        assert result["reason"] == "CHART_PERSISTENCE_FAILURE" and "SECRET" not in response.body
        assert app.review_store.load_current_chart(cycle) == prior
    _retain_later_current_run(app)
    before = _fingerprints(app.review_store.root)
    response, result = _send(routes, cycle, _image(color="green"))
    assert result["reason"] == "STALE_REVIEW_CYCLE"
    assert before == _fingerprints(app.review_store.root)


@pytest.mark.parametrize("case", ["png", "jpeg", "none", "text", "html", "unsupported", "ambiguous",
                                 "unfocused", "file", "large", "failed", "foreign_response"])
def test_explicit_clipboard_javascript(case):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js required for isolated JavaScript unit tests")
    script = _review_v2_chart_script().removeprefix("<script>").removesuffix("</script>")
    harness = r"""
const assert=require('node:assert/strict'); const vm=require('node:vm');
const test=process.argv[1], listeners={}, feedback={hidden:true,textContent:''}, requests=[];
const target={id:'chart-1',dataset:{uploadUrl:'/control/intraday-review/v2/chart?cycle=CYCLE-1'},
 attrs:{},addEventListener:(n,f)=>listeners[n]=f,focus:()=>document.activeElement=target,
 getAttribute:n=>target.attrs[n],setAttribute:(n,v)=>target.attrs[n]=v,removeAttribute:n=>delete target.attrs[n],
 hasAttribute:n=>n==='data-review-v2-chart',closest:()=>({id:'review-candidate-RESULT-1'})};
const file={type:test==='jpeg'?'image/jpeg':test==='unsupported'?'image/gif':'image/png',
 size:test==='large'?26214401:100};
const input={dataset:{target:'chart-1'},files:[file],addEventListener:(n,f)=>listeners['file-'+n]=f};
const document={activeElement:test==='unfocused'?null:target,
 getElementById:id=>id==='chart-1'?target:feedback,
 querySelectorAll:s=>s==='[data-review-v2-chart]'?[target]:[input]};
let reloads=0,focus='';
const context={document,URL,Set,Array,location:{href:'http://localhost/intraday/review',origin:'http://localhost',
 pathname:'/intraday/review',search:'?candidate=RESULT-1',reload:()=>reloads++},
 history:{replaceState:(_a,_b,url)=>focus=url},fetch:async(url,options)=>{
 requests.push({url,options});return {ok:test!=='failed',json:async()=>test==='failed'?{reason:'SECRET path'}:
 {outcome:'CHART_RECEIVED',cycle_identity:test==='foreign_response'?'OTHER':'CYCLE-1'}};}};
vm.runInNewContext(SCRIPT,context);
assert.equal(requests.length,0); // GET/registration never reads clipboard or sends bytes.
if(test==='file')listeners['file-change']();
else{let items=['none','text','html'].includes(test)?[{kind:'string',type:'text/plain',getAsFile:()=>{throw Error('TEXT READ')}}]:
 [{kind:'file',type:file.type,getAsFile:()=>file}]; if(test==='ambiguous')items.push(items[0]);
 listeners.paste({preventDefault(){},clipboardData:{items}});}
setImmediate(()=>{
 const good=['png','jpeg','file'].includes(test),sent=good||['failed','foreign_response'].includes(test);
 assert.equal(requests.length,sent?1:0);
 if(sent){assert.equal(requests[0].options.body,file);assert.equal(requests[0].url,'/control/intraday-review/v2/chart?cycle=CYCLE-1');}
 assert.equal(reloads,good?1:0);
 if(good)assert.equal(focus,'/intraday/review?candidate=RESULT-1#review-candidate-RESULT-1');
 else {assert.equal(feedback.hidden,false);assert(!feedback.textContent.includes('SECRET'));}
});
""".replace("SCRIPT", json.dumps(script))
    result = subprocess.run([node, "-e", harness, case], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
