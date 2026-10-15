"""TE-06A presentation only: local purple accents and decorative commodity marks."""

# This stylesheet is emitted only by Theta's page renderer. Shared shell source,
# state colours, intake markup/script and analytical contracts are not changed.
THEME_STYLES = """
.theta-theme{--theta-accent:#b3a6da;--theta-line:#413953;--theta-tint:#171c30;min-width:0}
.nav a.active[href="/theta-earners"]{background:linear-gradient(110deg,#342c4b,#24253c);box-shadow:inset 3px 0 #9281b7;color:#f2edf9}
.nav a.active[href="/theta-earners"] .icon{color:#b3a6da}
.title h1{text-transform:uppercase;letter-spacing:.045em;font-size:25px;overflow-wrap:anywhere}
.title h1::before{content:"Θ";color:#b3a6da;font-size:22px;margin-right:11px}
.title p{font-size:12px;line-height:1.5}
.theta-theme .theta-tabs{gap:24px;height:55px;border-color:var(--theta-line);margin-bottom:18px;overflow:visible}
.theta-theme .theta-tabs a{height:55px;min-width:118px;letter-spacing:.075em;font-size:12px}
.theta-theme .theta-tabs a.active{color:#e6dff4;border-color:#9281b7}
.theta-theme .theta-tabs a:hover{color:#e6dff4}
.theta-theme .theta-panel{border-color:var(--theta-line);background:linear-gradient(125deg,rgba(35,31,52,.46),rgba(7,24,39,.96) 65%);border-radius:12px;padding:22px;margin:16px 0;box-shadow:0 12px 30px rgba(0,0,0,.12)}
.theta-theme h2{font-size:18px;margin:0 0 14px;letter-spacing:.02em}
.theta-theme p{line-height:1.65;overflow-wrap:anywhere}
.theta-theme .theta-muted{color:#a0aebf;line-height:1.6}
.theta-theme .theta-summary{table-layout:fixed}
.theta-theme .theta-summary th{font-size:10px;letter-spacing:.09em;padding:10px 12px 14px;line-height:1.7}
.theta-theme .theta-summary th:first-child{width:23%}
.theta-theme .theta-summary th:last-child{width:17%}
.theta-theme .theta-summary td{padding:23px 12px;border-color:#293044;vertical-align:middle;overflow-wrap:anywhere}
.theta-theme .theta-summary tbody tr:last-child td{border-bottom:0}
.theta-theme .theta-summary tbody tr:hover{background:rgba(117,97,156,.055)}
.theta-theme .theta-subject{color:#e3e6ef;font-size:15px;font-weight:750}
.theta-theme a.theta-subject{display:flex;align-items:center;gap:12px;min-height:44px}
.theta-theme a.theta-subject:hover{color:var(--theta-accent)}
.theta-theme .theta-drill-arrow{color:var(--theta-accent);margin-left:auto;font-size:18px}
.theta-theme .theta-range{font-size:clamp(18px,1.7vw,25px);letter-spacing:-.035em;line-height:1.4;white-space:normal;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}
.theta-theme .theta-confidence{display:inline-block;font-size:11px;font-weight:650;border:1px solid #275044;background:rgba(27,73,51,.22);padding:4px 8px;border-radius:999px;margin-top:9px;color:var(--green)}
.theta-theme .theta-expiry{font-size:12px;margin-top:8px}
.theta-theme .theta-current{display:inline-block;border:1px solid #275044;background:rgba(27,73,51,.22);border-radius:999px;padding:3px 8px;margin-bottom:7px}
.theta-commodity-symbol{display:inline-grid;place-items:center;flex:0 0 42px;width:42px;height:42px;border:1px solid #464052;border-radius:11px;background:linear-gradient(145deg,#262536,#131f2e);color:#cbbb86}
.theta-commodity-symbol svg{width:28px;height:28px;display:block}
.theta-commodity-symbol[data-commodity="SILVERM"]{color:#b7c8d5}
.theta-commodity-symbol[data-commodity="COPPER"]{color:#c89978}
.theta-commodity-symbol[data-commodity="CRUDEOIL"]{color:#b3a6da}
.theta-commodity-symbol[data-commodity="NATURALGAS"]{color:#9aafd4}
.theta-theme .theta-empty{padding:64px 24px 70px;min-height:300px;text-align:center;background:radial-gradient(ellipse at 50% 0,rgba(103,81,139,.17),transparent 68%),#071827}
.theta-theme .theta-empty::before{content:"Θ";display:grid;place-items:center;width:52px;height:52px;margin:0 auto 23px;border:1px solid #4b405e;border-radius:14px;color:var(--theta-accent);background:#202238;font-size:30px}
.theta-theme .theta-empty h2{font-size:18px;font-weight:750;letter-spacing:.035em;line-height:1.5}
.theta-theme .theta-start,.theta-theme form[action="/theta-earners/question"] button{background:linear-gradient(140deg,#4a3e6b,#373652);border:1px solid #74638e;color:#f3eefb;padding:12px 18px;border-radius:8px;font-size:12px;letter-spacing:.04em;min-height:42px}
.theta-theme .theta-start:hover,.theta-theme form[action="/theta-earners/question"] button:hover{background:#514574;border-color:#a294bc}
.theta-theme button,.theta-theme .file-choice,.theta-theme .theta-actions a{background:#111e2f;border:1px solid #51465f;color:#d9d3e5;border-radius:7px;padding:8px 12px;min-height:36px}
.theta-theme button:hover,.theta-theme .file-choice:hover,.theta-theme .theta-actions a:hover{border-color:#8d7ca8;background:#23263b}
.theta-theme :is(a,button,input,select,summary,[tabindex]):focus-visible{outline:2px solid #b3a6da;outline-offset:4px}
.nav a.active[href="/theta-earners"]:focus-visible{outline:2px solid #b3a6da;outline-offset:3px}
.theta-theme input[type="checkbox"]{accent-color:#8574a7}
.theta-theme .theta-form{gap:14px;align-items:center}
.theta-theme .theta-form label{display:flex;align-items:center;gap:5px;min-height:36px;font-size:11px}
.theta-theme .theta-actions{gap:9px;margin:14px 0}
.theta-theme .theta-sandbox{font-size:10px;line-height:1.55;margin:0 0 12px;padding:6px 10px;border-left-color:#8c7333;background:rgba(80,62,26,.12);border-radius:0 5px 5px 0;color:#f6d997}
.theta-theme .theta-chart-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
.theta-theme .theta-chart-card{border-color:#3e374f;background:linear-gradient(140deg,#151d30,#091827 70%);padding:18px;border-radius:11px}
.theta-theme .theta-chart-card h3{color:#c0b3de;letter-spacing:.045em;font-size:17px}
.theta-theme .theta-chart-state{border:1px solid #3b4354;border-radius:999px;padding:3px 7px;font-size:10px;line-height:1.5}
.theta-theme .theta-chart-card[data-ready="true"] .theta-chart-state{border-color:#275044;background:rgba(27,73,51,.22)}
.theta-theme .theta-chart-guide{line-height:1.8;font-size:11px}
.theta-theme .theta-chart-preview img{max-height:340px;border-color:#40384f}
.theta-theme .theta-chart-preview span{display:block;color:#b3a6da;font-size:11px;margin-top:7px}
.theta-theme .chart-paste-target{background:#0b1626;border-color:#615375;min-height:100px}
.theta-theme .chart-paste-target:focus,.theta-theme .chart-paste-target.replace-ready{outline:2px solid #b3a6da;outline-offset:3px;border-color:transparent}
.theta-theme .chart-paste-target strong{color:#d0c5e3;font-size:12px;letter-spacing:.04em}
.theta-theme .theta-chart-question{border-color:#343347;color:#abb6c6;font-size:10px;line-height:1.6}
.theta-theme .theta-chart-counts{gap:8px;margin:16px 0}
.theta-theme .theta-chart-counts span{border:1px solid #373447;border-radius:6px;padding:7px 9px;font-size:10px;background:#101c2c}
.theta-theme .theta-macro-card{margin-top:16px;border-color:#51425f;background:linear-gradient(130deg,#242239,#0b1a2b 70%)}
.theta-theme .theta-pack-controls summary{font-size:12px;line-height:1.7;color:#d3c8e6;overflow-wrap:anywhere}
.theta-theme .theta-detail h3{color:#d6cbe7;font-size:15px;line-height:1.6;margin-top:22px;overflow-wrap:anywhere}
.theta-theme .theta-detail h2{display:flex;align-items:center;gap:12px;flex-wrap:wrap;line-height:1.6}
.theta-theme .theta-detail a{color:#b9add8;text-decoration:underline;text-underline-offset:3px}
.theta-theme .theta-id{line-height:1.7;color:#a0aebf}
.theta-outlook .theta-outlook-subject{display:flex;align-items:center;gap:12px}
.theta-outlook .theta-subject>span:not(.theta-commodity-symbol){white-space:nowrap}
.theta-outlook .theta-confidence{border:0;border-radius:0;background:none;color:#d8d1e9;padding:0;font-size:14px;font-weight:600}
.theta-outlook .theta-range{font-size:clamp(20px,1.8vw,27px);color:#eee8f6}
.theta-outlook .theta-outlook-state{font-size:11px;color:#b5a8d2;line-height:1.7}
.theta-outlook .theta-documentary{display:grid;gap:3px;margin-top:15px;color:#b6a9cc}
.theta-outlook .theta-documentary>span{font-size:8px;letter-spacing:.06em;color:#94a0b4}
.theta-outlook .theta-documentary>strong{font-size:11px;font-weight:600;letter-spacing:.04em}
.theta-outlook .theta-documentary>small{font-size:10px;color:#94a0b4}
.theta-outlook .theta-outlook-explanation{margin-top:18px}
@media(max-width:1100px){.theta-theme .theta-summary td{padding:18px 8px}.theta-theme .theta-summary th{padding-left:8px;padding-right:8px}.theta-theme a.theta-subject{gap:7px;flex-wrap:wrap}.theta-theme .theta-subject{font-size:12px}.theta-theme .theta-commodity-symbol{flex-basis:32px;width:32px;height:32px}.theta-theme .theta-commodity-symbol svg{width:22px;height:22px}}
@media(max-width:760px){.topbar .title{min-width:0}.title h1{font-size:21px}.title p{font-size:10px}.theta-theme .theta-panel{padding:17px}.theta-theme .theta-chart-grid{grid-template-columns:minmax(0,1fr)}.theta-theme .theta-tabs{gap:16px}.theta-theme .theta-summary thead{display:none}.theta-theme .theta-summary,.theta-theme .theta-summary tbody{display:block}.theta-theme .theta-summary tr{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;border-bottom:1px solid #293044;padding:18px 0}.theta-theme .theta-summary tr:last-child{border-bottom:0}.theta-theme .theta-summary td{display:block;border:0;padding:0}.theta-theme .theta-summary td:first-child,.theta-theme .theta-summary td:last-child{grid-column:1/-1}.theta-theme .theta-summary td:nth-child(2)::before{content:"E1 · NEXT EXPIRY"}.theta-theme .theta-summary td:nth-child(3)::before{content:"E2 · SECOND-NEXT EXPIRY"}.theta-theme .theta-summary td:nth-child(2)::before,.theta-theme .theta-summary td:nth-child(3)::before{display:block;font-size:9px;letter-spacing:.04em;color:#a0aebf;margin-bottom:7px}.theta-theme .theta-subject{font-size:15px}.theta-theme .theta-range{font-size:20px}.theta-theme .theta-summary td:last-child>br{display:none}.theta-theme .theta-summary td:last-child time{display:inline-block;vertical-align:middle}.theta-theme .theta-current{margin-right:8px}.theta-theme .theta-empty{padding:45px 15px}.theta-theme .theta-empty h2{font-size:16px}.theta-theme .theta-form{align-items:flex-start}.theta-theme .theta-actions a{overflow-wrap:anywhere;max-width:100%}}
"""


# Sponsor five-row refinement. Emitted only for the V3 Outlook, never for
# New Analysis, Detail, the legacy reader or another product's shared shell.
OUTLOOK_STYLES = """
.theta-theme .theta-outlook{padding:18px 20px}
.theta-theme .theta-outlook h2{margin-bottom:5px}
.theta-outlook>p.theta-muted{font-size:11px;line-height:1.6;margin:8px 0}
.theta-outlook .theta-summary th{letter-spacing:.035em;padding:8px 12px 10px;font-size:11px}
.theta-outlook .theta-summary td{padding:9px 12px;border-color:#253345}
.theta-outlook .theta-range{font-size:clamp(16px,1.35vw,19px);line-height:1.3;letter-spacing:-.025em}
.theta-outlook .theta-confidence{font-size:11.5px;line-height:1.5;margin:3px 0 0}
.theta-outlook .theta-expiry{font-size:11.5px;line-height:1.5;margin-top:2px}
.theta-outlook .theta-documentary{display:block;margin-top:4px}
.theta-outlook .theta-assessment-badge{display:inline-block;border:1px solid #49415d;border-radius:6px;padding:2px 8px;font-size:10px;line-height:1.5;font-weight:650;letter-spacing:.025em;color:#d4cae8;background:rgba(96,79,135,.2)}
.theta-outlook .theta-assessment-badge[data-state="DOCUMENTED"]{border-color:#285348;color:#a6d8c8;background:rgba(37,93,78,.24)}
.theta-outlook .theta-assessment-badge[data-state="LIMITED"]{border-color:#67552f;color:#e2ca90;background:rgba(117,88,33,.24)}
.theta-outlook .theta-documentary>small{display:block;margin-top:3px}
.theta-outlook .theta-analysis{font-size:10.5px;line-height:1.5}
.theta-outlook .theta-outlook-state{color:#ddd7e9;font-size:10.5px;line-height:1.5;white-space:nowrap}
.theta-outlook .theta-analysis time{display:inline-block;margin-top:3px}
.theta-outlook .theta-view-details{display:block;width:fit-content;margin-top:5px;color:var(--theta-accent);font-size:12px;font-weight:650;line-height:1.5}
.theta-outlook .theta-view-details:hover{text-decoration:underline;text-underline-offset:3px}
.theta-outlook .theta-outlook-explanation{margin-top:14px}
@media(min-width:761px){.theta-outlook .theta-summary tr:has([data-theta-horizon]){height:112px}}
@media(min-width:761px) and (max-width:1100px){.theta-outlook .theta-summary th:first-child{width:23%}.theta-outlook .theta-summary th:last-child{width:17%}.theta-outlook .theta-summary th,.theta-outlook .theta-summary td{padding-left:7px;padding-right:7px}.theta-outlook .theta-subject{font-size:12px}.theta-outlook a.theta-subject{gap:6px;flex-wrap:nowrap}.theta-outlook .theta-commodity-symbol{flex-basis:28px;width:28px;height:28px}.theta-outlook .theta-commodity-symbol svg{width:20px;height:20px}.theta-outlook .theta-drill-arrow{font-size:15px}.theta-outlook .theta-outlook-state{white-space:normal}}
@media(max-width:760px){.theta-outlook .theta-summary td{padding:0}.theta-outlook .theta-summary tr{padding:13px 0}.theta-outlook .theta-range{font-size:16px}.theta-outlook .theta-subject{font-size:14px}.theta-outlook .theta-summary td:last-child time{display:block}}
"""


def commodity_symbol(subject):
    """Fixed local SVGs are decoration only; never evidence or price series."""
    marks = {
        'GOLDM': '<path d="M5 15l3-6h9l3 6M5 15h15l2 7H3l2-7zM8 9l3-6h9l3 6H8zM12 9l2 6M10 15l-1 7M17 15l2 7"/>',
        'SILVERM': '<path d="M5 15l3-6h9l3 6M5 15h15l2 7H3l2-7zM8 9l3-6h9l3 6H8zM12 9l2 6M10 15l-1 7M17 15l2 7"/>',
        'COPPER': '<ellipse cx="9" cy="13" rx="6" ry="8"/><ellipse cx="9" cy="13" rx="3" ry="5"/><path d="M9 5h8c3 0 6 3.6 6 8s-3 8-6 8H9M14 5c3 0 6 3.6 6 8s-3 8-6 8"/>',
        'CRUDEOIL': '<ellipse cx="13" cy="5" rx="7" ry="3"/><path d="M6 5v16c0 1.7 3.1 3 7 3s7-1.3 7-3V5M6 10h14M6 19h14M13 11s-3 3-3 5a3 3 0 006 0c0-2-3-5-3-5z"/>',
        'NATURALGAS': '<path d="M14 2c2 6-4 6-1 11 2-1 3-3 3-5 5 5 7 9 4 13-3 5-11 5-14 0C2 15 9 10 10 7c0 4 1 5 2 5-2-5 2-6 2-10zM13 15c-4 4-3 7 0 8 3-1 4-4 0-8z"/>',
    }
    return (f'<span class="theta-commodity-symbol" data-commodity="{subject}" aria-hidden="true">'
            '<svg viewBox="0 0 26 28" fill="none" stroke="currentColor" stroke-width="1.4" '
            'stroke-linecap="round" stroke-linejoin="round" focusable="false">'
            + marks[subject] + '</svg></span>')
