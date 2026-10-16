"""Local controls over rendered Intraday evidence; no operational dependencies."""
from html import escape


def table_controls(identity, *, diagnostic=False):
    """All choices are populated from the displayed rows, without store reads."""
    def field(name, label, element):
        key = identity + '-' + name
        return ('<label for="' + key + '">' + label + '</label>'
                + element.replace('CONTROL', 'id="' + key + '" data-filter="' + name + '"'))

    select = '<select CONTROL><option value="">All</option></select>'
    fields = [field('security', 'Security search', '<input CONTROL type="search" autocomplete="off">')]
    for name, label in (('direction', 'Direction'), ('score', 'Score'), ('status', 'Status'),
                        ('waiting', 'Waiting for'), ('monitoring', 'Monitoring')):
        fields.append(field(name, label, select))
    for name, label in (('minimum', 'Minimum Assessment Price'), ('maximum', 'Maximum Assessment Price')):
        fields.append(field(name, label, '<input CONTROL type="text" inputmode="decimal" autocomplete="off">'))
    sort = ''.join('<option value="' + value + '">' + escape(label) + '</option>' for value, label in (
        ('original', 'Original order'), ('security-asc', 'Security · A–Z'), ('security-desc', 'Security · Z–A'),
        ('score-desc', 'Score · highest first'), ('score-asc', 'Score · lowest first'),
        ('price-asc', 'Assessment Price · lowest first'), ('price-desc', 'Assessment Price · highest first')))
    return ('<div class="machine-controls" hidden><fieldset><legend>Find and compare assessments</legend>'
        + '<div class="control-grid">' + ''.join('<div>' + field + '</div>' for field in fields)
        + '<div>' + field('sort', 'Sort rows', '<select CONTROL>' + sort + '</select>') + '</div></div>'
        + ('<label><input type="checkbox" id="secondary-review-only" data-filter="secondary"> Secondary Review only</label>' if diagnostic else '')
        + '<button type="button" data-clear-controls>Clear All</button>'
        + '<p class="secondary">Local display only. Sorting is not a trading recommendation.</p>'
        + '<p role="status" aria-live="polite" data-filter-count></p></fieldset></div>'
        + '<noscript><p>All retained rows are shown. Search, filtering and sorting require JavaScript; evidence and expandable details remain readable.</p></noscript>'
        + '<p data-filter-empty hidden>No assessments match these filters. Use Clear All to restore this population.</p>')


CONTROLS_CSS = """
.machine-review .control-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:9px}
.machine-review .machine-controls fieldset{border:1px solid #375365;border-radius:6px;padding:12px;margin:12px 0}
.machine-review .control-grid label{display:block;font-size:11px;margin-bottom:4px}
.machine-review .control-grid input,.machine-review .control-grid select{box-sizing:border-box;width:100%;min-height:34px;background:#102b3d;color:#dce8f0;border:1px solid #426076;border-radius:4px;padding:5px}
.machine-review .machine-controls button{margin:10px;min-height:34px;padding:5px 12px}
.machine-review .assessment-browser [hidden]{display:none!important}
"""


CONTROLS_JS = r"""
function decimal(value){
 if(typeof value!=='string'||value.length>512)return null;
 const m=value.trim().match(/^([+-]?)(\d+(?:\.\d*)?|\.\d+)(?:[eE]([+-]?\d+))?$/);
 if(!m)return null;
 const exponent=Number(m[3]||0);if(!Number.isInteger(exponent)||Math.abs(exponent)>1000)return null;
 const parts=m[2].split('.');let digits=(parts[0]+(parts[1]||'')).replace(/^0+/,'');
 if(!digits)return {sign:0,digits:'0',scale:0};
 let scale=(parts[1]||'').length-exponent;
 while(digits.endsWith('0')){digits=digits.slice(0,-1);scale--;}
 return {sign:m[1]==='-'?-1:1,digits,scale};
}
function compareDecimal(a,b){
 if(a.sign!==b.sign)return a.sign-b.sign;if(!a.sign)return 0;
 const lengthA=a.digits.length-a.scale,lengthB=b.digits.length-b.scale;
 if(lengthA!==lengthB)return Math.sign(lengthA-lengthB)*a.sign;
 const width=Math.max(a.digits.length,b.digits.length),x=a.digits.padEnd(width,'0'),y=b.digits.padEnd(width,'0');
 return (x===y?0:x<y?-1:1)*a.sign;
}
function matches(row,f){
 const price=decimal(row.price);
 return (!f.security||row.security.toLowerCase().includes(f.security.toLowerCase()))
  &&(!f.direction||row.direction===f.direction)&&(!f.score||row.score===f.score)
  &&(!f.status||row.status===f.status)&&(!f.waiting||row.waiting.includes(f.waiting))
  &&(!f.monitoring||row.monitoring===f.monitoring)&&(!f.secondary||row.secondary)
  &&(!f.minimum||(price!==null&&compareDecimal(price,decimal(f.minimum))>=0))
  &&(!f.maximum||(price!==null&&compareDecimal(price,decimal(f.maximum))<=0));
}
function compareRows(a,b,sort){
 const [key,direction]=sort.split('-'),sign=direction==='desc'?-1:1;
 let compared=0;
 if(key==='security')compared=(a.security.toLowerCase()<b.security.toLowerCase()?-1:a.security.toLowerCase()>b.security.toLowerCase()?1:0)*sign;
 else if(key==='score'||key==='price'){
  const x=decimal(a[key]),y=decimal(b[key]);
  // Missing, unavailable and not-applicable are always last, never numerical zero.
  if(x===null&&y!==null)return 1;if(x!==null&&y===null)return -1;
  compared=x===null?0:compareDecimal(x,y)*sign;
 }
 return compared||a.order-b.order;
}
if(typeof module!=='undefined'&&module.exports)module.exports={decimal,compareDecimal,matches,compareRows};
if(typeof document!=='undefined')document.querySelectorAll('[data-assessment-browser]').forEach(browser=>{
 const controls=browser.querySelector('.machine-controls');if(!controls)return;
 const rows=Array.from(browser.querySelectorAll('tr[data-assessment-controls]')).map((main,order)=>({
  main,detail:main.nextElementSibling,data:{...JSON.parse(main.dataset.assessmentControls),order}}));
 const fields=Object.fromEntries(Array.from(controls.querySelectorAll('[data-filter]')).map(input=>[input.dataset.filter,input]));
 ['direction','score','status','waiting','monitoring'].forEach(key=>{
  const values=[...new Set(rows.flatMap(row=>key==='waiting'?row.data.waiting:[row.data[key]]))];
  values.sort((a,b)=>a.localeCompare(b)).forEach(value=>{
   const option=document.createElement('option');option.value=value;
   option.textContent=key==='score'&&/^[0-5]$/.test(value)?value+'/5':value.replaceAll('_',' ');
   fields[key].append(option);
  });
 });
 const count=controls.querySelector('[data-filter-count]'),empty=browser.querySelector('[data-filter-empty]');
 function update(){
  const f=Object.fromEntries(Object.entries(fields).map(([key,input])=>[key,input.type==='checkbox'?input.checked:input.value.trim()]));
  const invalid=['minimum','maximum'].some(key=>f[key]&&decimal(f[key])===null)
   ||(f.minimum&&f.maximum&&decimal(f.minimum)&&decimal(f.maximum)&&compareDecimal(decimal(f.minimum),decimal(f.maximum))>0);
  if(invalid){count.textContent='Enter valid Assessment Price bounds; minimum must not exceed maximum.';return;}
  const sorted=[...rows].sort((a,b)=>compareRows(a.data,b.data,f.sort));let visible=0;
  const fragment=document.createDocumentFragment();
  sorted.forEach(row=>{const hidden=!matches(row.data,f);row.main.hidden=hidden;row.detail.hidden=hidden;
   if(!hidden)visible++;fragment.append(row.main,row.detail);});
  browser.querySelector('tbody').append(fragment);
  count.textContent='Showing '+visible+' of '+rows.length+' · '+browser.dataset.population;
  empty.hidden=visible!==0;
 }
 controls.addEventListener('input',update);controls.addEventListener('change',update);
 controls.querySelector('[data-clear-controls]').addEventListener('click',()=>{
  Object.entries(fields).forEach(([key,input])=>{if(input.type==='checkbox')input.checked=false;else input.value=key==='sort'?'original':'';});update();
 });
 controls.hidden=false;update();
});
"""
