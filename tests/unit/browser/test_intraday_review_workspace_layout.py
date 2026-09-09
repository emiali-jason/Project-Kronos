"""Isolated real-browser layout evidence; no production server or stores.

Exports fixture pages under published isolation; a separately kernel-sandboxed
Browser consumes only these fixtures for full visual qualification.
"""
from dataclasses import replace
import json
import os
from pathlib import Path
import struct
import zlib
import pytest
from kronos.browser.intraday_views import render_intraday_review
from tests.unit.browser.test_intraday_review_workflow import _routes
from tests.unit.browser.test_intraday_review_v2_control import _payload
from tests.unit.browser.test_product_route_isolation import _snapshot


def composite(width, height, rows):
    # Synthetic evidence: simple panel grid, never represented as market data.
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    pixels = b''.join(b'\0'+b''.join(bytes((35,90,75)) if x%(width//4)<3 or y%(height//rows)<3
        else bytes((12,25,36)) for x in range(width)) for y in range(height))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))
            +chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b''))


BROWSER_SCRIPT = r"""
const fs=require('fs');const assert=require('assert');const {chromium}=require('playwright');
(async()=>{
 const cfg=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));
 const browser=await chromium.launch({headless:true,executablePath:process.env.WO07D_BROWSER_EXECUTABLE,args:['--no-sandbox','--disable-background-networking']});
 const context=await browser.newContext({viewport:{width:cfg.width,height:1100},serviceWorkers:'block'});
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await context.route('**/*',route=>{
  const u=new URL(route.request().url());
  if(u.pathname==='/fixture')return route.fulfill({contentType:'text/html',body:fs.readFileSync(cfg.html,'utf8')});
  if(u.pathname.endsWith('/chart-preview'))return route.fulfill({contentType:'image/png',body:fs.readFileSync(u.searchParams.get('cycle')==='CYCLE-8'?cfg.mcx:cfg.nse)});
  if(u.pathname==='/assets/brand/kronos-brand-mark.png'||u.pathname==='/favicon.png')return route.fulfill({contentType:'image/png',body:fs.readFileSync(cfg.brand)});
  if(u.pathname==='/status')return route.fulfill({status:503,body:'Isolated fixture'});
  return route.fulfill({status:204,body:''});
 });
 await page.goto('http://wo07d.invalid/fixture');await page.locator('.intraday-review-v2').waitFor();
 await page.locator('img').evaluateAll(imgs=>imgs.forEach(i=>i.loading='eager'));
 await page.locator('img').evaluateAll(imgs=>Promise.all(imgs.map(i=>i.complete?Promise.resolve():new Promise(r=>{i.onload=r;i.onerror=r}))));
 const layout=await page.evaluate(()=>{
  const cards=[...document.querySelectorAll('.intraday-review-v2-card')];const rects=cards.map(c=>{const r=c.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}});
  const columns=rects.length?rects.filter(r=>Math.abs(r.y-rects[0].y)<2).length:0;
  const images=[...document.querySelectorAll('.intraday-chart-preview img')].map(i=>({w:i.width,h:i.height,nw:i.naturalWidth,nh:i.naturalHeight}));
  return {columns,rects,images,overflow:document.documentElement.scrollWidth>innerWidth,
   stretched:getComputedStyle(document.querySelector('.intraday-review-v2-grid')).alignItems,
   lineageOpen:document.querySelectorAll('.intraday-review-diagnostics[open]').length,
   bulk:document.querySelectorAll('[data-current-review-bulk]').length};
 });
 assert(!layout.overflow,JSON.stringify(layout));assert.strictEqual(layout.columns,cfg.columns);assert.strictEqual(layout.lineageOpen,0);
 assert.strictEqual(layout.stretched,'start');for(const i of layout.images){assert(i.nw>0);assert(Math.abs(i.w/i.h-i.nw/i.nh)<0.04)}
 for(let i=0;i<layout.rects.length;i++)for(let j=i+1;j<layout.rects.length;j++){const a=layout.rects[i],b=layout.rects[j];assert(a.x+a.w<=b.x+1||b.x+b.w<=a.x+1||a.y+a.h<=b.y+1||b.y+b.h<=a.y+1)}
 if(layout.rects.length){
  assert(await page.getByRole('heading',{name:'M&M',exact:true}).isVisible());
  const disclosure=page.locator('.intraday-review-diagnostics summary').first();await disclosure.click();assert(await page.locator('.intraday-review-diagnostics').first().getAttribute('open')!==null);await disclosure.click();
  const link=page.locator('.intraday-chart-preview').first();const popupPromise=context.waitForEvent('page');await link.click();const popup=await popupPromise;await popup.waitForLoadState();assert(popup.url().includes('revision='));await popup.close();
 }
 assert.deepStrictEqual(errors,[]);await page.screenshot({path:cfg.screenshot,fullPage:true});
 fs.writeFileSync(cfg.result,JSON.stringify({...layout,errors},null,2));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
"""


@pytest.mark.parametrize('width,state,columns',[(1536,'REVIEW_CURRENT',4),(1280,'REVIEW_CURRENT',3),
    (390,'REVIEW_CURRENT',1),(1536,'NEW_PROBABLES_AVAILABLE',0),(390,'REVIEW_ABSENT',0)])
def test_browser_layout(tmp_path,width,state,columns):
    run,app,control,routes=_routes(tmp_path/'stores')
    control.execute_document(_payload(run))
    current=app.snapshot();base=current.candidates[0]
    labels=['M&M','NIFTY','BANKNIFTY','LONG CANDIDATE IDENTITY FOR LEGIBILITY','TITAN','SRF','BDL','NTPC','CRUDE']
    candidates=tuple(replace(base,sponsor_label=label,probable_result_identity=f'RESULT-{i}',cycle_identity=f'CYCLE-{i}',
        canonical_subject_identity='MCX-SUBJECT-CRUDE' if i==8 else label,direction='SHORT' if i%2 else 'LONG',
        chart_state='CHART_READY' if i in {0,1,8} else 'CHART_REQUIRED',chart_revision_identity=f'CHART-{i}' if i in {0,1,8} else None,
        chart_revision_ordinal=4 if i in {0,1,8} else None,question_transport_identity='TRANSPORT' if i==1 else None,
        question_pack_state='TRANSPORT_READY' if i==1 else 'ABSENT',
        question_filename='EXACT-QUESTION-'+('A'*60)+'.pdf',expected_answer_filename='EXACT-ANSWER-'+('B'*60)+'.json',
        native_contract_identity='MCX-FUT-CRUDE-EXACT-GOVERNED-CONTRACT' if i==8 else None,
        reference_context_identity='NYMEX:CL1!' if i==8 else None,native_binding_identity='EXACT-BINDING' if i==8 else None)
        for i,label in enumerate(labels))
    status=dict(control.status_document(),currentness_state=state,current_review_candidate_count=9,current_probables_candidate_count=9,
        workspace_state={'REVIEW_CURRENT':'CURRENT_REVIEW_LOADED','REVIEW_ABSENT':'NO_REVIEW_LOADED','NEW_PROBABLES_AVAILABLE':'REVIEW_NON_CURRENT'}[state])
    html=render_intraday_review(_snapshot(),routes._review.snapshot(),review_v2=replace(current,candidates=candidates),
        available_probables_v2_run=run,review_v2_status=status)
    html=html.replace('<h2>Current Review workspace</h2>','<h2>Current Review workspace</h2><p>ISOLATED ENGINEERING FIXTURE · synthetic panel images</p>')
    (tmp_path/'brand.png').write_bytes(Path('assets/images/brand/kronos-brand-mark.png').read_bytes())
    (tmp_path/'page.html').write_text(html);(tmp_path/'nse.png').write_bytes(composite(800,240,1));(tmp_path/'mcx.png').write_bytes(composite(800,480,2))
    artifact=Path(os.environ.get('WO07D_ARTIFACT_DIR',str(tmp_path)));artifact.mkdir(parents=True,exist_ok=True)
    cfg={'width':width,'columns':columns,'html':str(tmp_path/'page.html'),'nse':str(tmp_path/'nse.png'),'mcx':str(tmp_path/'mcx.png'),'brand':str(tmp_path/'brand.png'),
        'screenshot':str(artifact/f'{state}-{width}.png'),'result':str(artifact/f'{state}-{width}.json')}
    # Fixture generation runs under published Test Isolation Hardening. Browser
    # rendering is a separate kernel-sandboxed qualification over these exports.
    if os.environ.get('WO07D_ARTIFACT_DIR'):
        key=f'{state}-{width}'
        for source in ('page.html','nse.png','mcx.png','brand.png'):
            destination=artifact/f'{key}-{source}'
            destination.write_bytes((tmp_path/source).read_bytes())
            cfg[{'page.html':'html','nse.png':'nse','mcx.png':'mcx','brand.png':'brand'}[source]]=str(destination)
        (artifact/f'{key}-browser.json').write_text(json.dumps(cfg))
        (artifact/'layout-browser.js').write_text(BROWSER_SCRIPT)
    assert '<div class="intraday-review-v2-grid">' in html
    assert html.count('<article class="intraday-review-v2-card"')==(9 if state=='REVIEW_CURRENT' else 0)
