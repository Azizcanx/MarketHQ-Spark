import json
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = 8000
BACKEND_BASE = "http://127.0.0.1:8010"

HTML = """
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>MarketHQ — Strategy Explorer</title>
<style>
:root{--bg:#f4f6f8;--card:#fff;--soft:#fafbfc;--line:#dfe5eb;--text:#111;--muted:#59616a;--green:#148a5d;--green-soft:#eaf8f1;--amber:#9a6a07;--amber-soft:#fff6dc;--red:#b6314d;--red-soft:#fff0f3;--blue:#2c69b8;--blue-soft:#edf4ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,Segoe UI,Arial,sans-serif;font-size:13px;line-height:1.45}
button{font:inherit;cursor:pointer}.top{position:sticky;top:0;z-index:10;height:60px;background:#fff;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:10px;padding:0 22px}.logo{font-weight:900;font-size:20px}.sub{font-size:9px;font-weight:900;color:var(--muted);letter-spacing:1px}.grow{flex:1}
.pill,.tag{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:5px 9px;font-size:8px;font-weight:900}.safe{background:var(--green-soft);color:var(--green)}.bad{background:var(--red-soft);color:var(--red)}.warn{background:var(--amber-soft);color:var(--amber)}.info{background:var(--blue-soft);color:var(--blue)}
.btn{border:1px solid #cfd6de;background:#fff;border-radius:8px;padding:8px 11px;font-size:10px;font-weight:900}.btn:hover{background:#fafbfd}
.chart-buttons{display:flex;gap:5px;flex-wrap:wrap}
.chart-button{border:1px solid #cfd6de;background:#fff;border-radius:999px;padding:5px 8px;font-size:8px;font-weight:900}
.chart-button.active{background:#111;color:#fff;border-color:#111}
.trade-select{border:1px solid #cfd6de;background:#fff;border-radius:8px;padding:6px 8px;font-size:8px;font-weight:900;max-width:180px}
.trade-metrics{grid-template-columns:repeat(6,1fr)}
.trade-row{cursor:pointer}
.trade-row:hover{background:#f1f4f6}
.trade-row.selected{outline:2px solid #111;outline-offset:-2px}
.trade-detail-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-top:10px}
.trade-chart-box{margin-top:10px}
.trade-chart{height:430px;margin-top:8px;overflow:hidden;background:#fff;border:1px solid var(--line);border-radius:8px}

.trade-chart-box{margin-top:10px}.trade-chart{height:470px;margin-top:8px;overflow:hidden;background:#fff;border:1px solid var(--line);border-radius:8px}
.trade-filter-note{font-size:8px;color:var(--muted)}
.trade-toolbar{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:8px}
.trade-toolbar .chart-button{padding:5px 9px}
.trade-summary{display:grid;grid-template-columns:repeat(6,1fr);gap:7px;margin-top:9px}
.trade-summary .metric{min-height:58px}
.trade-empty{display:flex;align-items:center;justify-content:center;height:100%;color:var(--muted);font-size:10px}
.trade-levels{display:flex;gap:5px;flex-wrap:wrap;margin-top:7px}
.trade-level{font-size:8px;font-weight:900;padding:4px 7px;border-radius:999px;border:1px solid var(--line);background:#fff}
.trade-level.entry{border-color:#b8d0ef;color:#2c69b8}.trade-level.exit{border-color:#c7cbd0;color:#111}.trade-level.sl{border-color:#efc2cb;color:#b6314d}.trade-level.tp{border-color:#bfe2cf;color:#148a5d}
@media(max-width:1250px){.trade-summary{grid-template-columns:repeat(3,1fr)}}
@media(max-width:800px){.trade-summary{grid-template-columns:repeat(2,1fr)}}


.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.chart-card{background:var(--soft);border:1px solid var(--line);border-radius:9px;padding:10px;min-width:0}
.chart-card.wide{grid-column:1/-1}
.chart-title{font-size:10px;font-weight:900}.chart-subtitle{font-size:8px;color:var(--muted);margin-top:2px}
.svg-wrap{width:100%;height:300px;overflow:auto;margin-top:6px}.svg-wrap.tall{height:340px}.svg-wrap svg{width:100%;height:100%;display:block}
.pnl-chart-wrap{position:relative}.pnl-point{cursor:pointer}.pnl-point:hover{stroke-width:3}.pnl-selected{stroke-width:4}.pnl-note{font-size:7px;fill:#69737d}
.chart-label{font:9px Inter,Segoe UI,Arial,sans-serif;fill:#4e5861}.chart-value{font:8px Inter,Segoe UI,Arial,sans-serif;fill:#4e5861}.chart-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}.chart-mini-meta{font-size:8px;font-weight:900;color:#66717c;white-space:nowrap}.chart-inline-controls{display:flex;gap:5px;margin-top:7px}.chart-inline-controls .chart-button{padding:4px 7px}
.chart-axis{stroke:#cfd6de;stroke-width:1}.chart-gridline{stroke:#e9edf1;stroke-width:1}.chart-zero{stroke:#aeb8c1;stroke-width:1}
.regime-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.regime-timeline{height:150px;margin-top:8px;display:grid;grid-auto-flow:column;grid-auto-columns:minmax(7px,1fr);gap:2px;align-items:stretch;background:#eef2f5;border:1px solid var(--line);border-radius:8px;padding:6px;overflow:hidden}.regime-seg{border-radius:3px;min-width:3px;position:relative}.regime-seg span{position:absolute;inset:auto 3px 3px 3px;font-size:6px;font-weight:900;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.regime-trend-up{background:#dbeeff}.regime-trend-down{background:#ffe1e7}.regime-sideways{background:#eef1f4}.regime-high-vol{box-shadow:inset 0 0 0 2px #9a6a07}.regime-table{display:grid;gap:6px;margin-top:8px}.regime-row,.stress-row{display:grid;grid-template-columns:1fr repeat(4,auto);gap:8px;align-items:center;padding:7px 8px;border:1px solid var(--line);border-radius:8px;background:#fff;font-size:8px}.regime-row strong{font-size:9px}.regime-chip{display:inline-flex;align-items:center;padding:3px 6px;border-radius:999px;font-size:7px;font-weight:900;text-transform:uppercase}.regime-up{background:var(--blue-soft);color:var(--blue)}.regime-down{background:var(--red-soft);color:var(--red)}.regime-flat{background:#eef1f4;color:#59616a}.regime-vol{background:var(--amber-soft);color:var(--amber)}.stress-panel{display:grid;gap:6px;margin-top:8px}.stress-kpi{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:6px}.stress-kpi .metric{min-height:58px}.stress-row{grid-template-columns:1fr 1fr 1fr}.stress-row .positive{color:var(--green);font-weight:900}.stress-row .negative{color:var(--red);font-weight:900}.dd-duration-bar{height:10px;background:#eef1f4;border-radius:999px;overflow:hidden}.dd-duration-fill{height:100%;background:#b6314d;border-radius:999px}.research-footnote{font-size:8px;color:#6a747e;margin-top:10px}.regime-timeline-meta{font-size:8px}.
@media(max-width:1000px){.regime-grid{grid-template-columns:1fr}}
.diagnostics-grid{display:grid;grid-template-columns:1.2fr 1fr;gap:10px}.diagnostic-card{background:var(--soft);border:1px solid var(--line);border-radius:9px;padding:10px;min-width:0}.diag-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:8px}.diag-kpi{background:#fff;border:1px solid var(--line);border-radius:8px;padding:8px}.diag-kpi .n{font-size:14px;font-weight:900;margin-top:3px}.diag-chart{height:290px;margin-top:8px;overflow:auto}.diag-chart svg{width:100%;height:100%;display:block}.diag-note{font-size:8px;color:var(--muted);margin-top:7px}.streak-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px}.streak-box{background:#fff;border:1px solid var(--line);border-radius:8px;padding:9px}.streak-bars{display:grid;gap:5px;margin-top:8px}.streak-row{display:grid;grid-template-columns:82px 1fr 42px;gap:6px;align-items:center;font-size:8px}.streak-track{height:8px;background:#edf0f3;border-radius:999px;overflow:hidden}.streak-fill{height:100%;border-radius:999px}.diag-foot{font-size:8px;color:#6a747e;margin-top:10px}@media(max-width:1100px){.diagnostics-grid{grid-template-columns:1fr}.diag-kpis{grid-template-columns:repeat(2,1fr)}}


.wrap{max-width:1540px;margin:auto;padding:22px}.hero{display:flex;gap:18px;align-items:flex-start}.hero h1{font-size:30px;line-height:1.05;margin:4px 0 8px;letter-spacing:-1px}.hero p{margin:0;color:#444;font-size:12px}.actions{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}
.nav{display:flex;gap:6px;flex-wrap:wrap;margin:16px 0}.nav a{text-decoration:none;color:#111;background:#fff;border:1px solid var(--line);border-radius:999px;padding:6px 10px;font-size:9px;font-weight:900}
.kpis{display:grid;grid-template-columns:repeat(8,1fr);gap:9px}.kpi,.card{background:#fff;border:1px solid var(--line);border-radius:10px;box-shadow:0 7px 24px rgba(24,34,44,.055)}.kpi{padding:12px;min-height:82px}.label{font-size:8px;color:#545c64;font-weight:900;text-transform:uppercase;letter-spacing:.8px}.value{font-size:22px;font-weight:900;margin-top:6px}
.card{margin-top:16px}.head{display:flex;align-items:center;gap:8px;padding:13px 15px;border-bottom:1px solid var(--line)}.head h2{margin:0;font-size:12px}.muted{font-size:9px;color:var(--muted)}.body{padding:14px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:10px}.three{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.box{background:var(--soft);border:1px solid var(--line);border-radius:9px;padding:11px}.cap{font-size:8px;text-transform:uppercase;letter-spacing:.7px;font-weight:900;color:#555e68}.big{font-size:18px;font-weight:900;margin-top:4px}.small{font-size:9px;color:#525c66;margin-top:4px}
.metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:8px}.metric{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:9px}.metric .n{font-size:15px;font-weight:900;margin-top:3px}
.tablewrap{overflow:auto}table{width:100%;border-collapse:collapse;min-width:860px}th,td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;font-size:8px;vertical-align:top}th{font-size:7px;background:var(--soft);color:#555;text-transform:uppercase;letter-spacing:.7px}
.bar{height:8px;background:#e8edf1;border-radius:999px;overflow:hidden}.fill{height:100%;background:#111}.scoreline{display:grid;grid-template-columns:140px 1fr 55px;gap:8px;align-items:center;margin:9px 0;font-size:8px;font-weight:900}
.list{display:grid;gap:7px}.row{background:var(--soft);border:1px solid var(--line);border-radius:8px;padding:9px}.rowtop{display:flex;align-items:center;gap:7px}.rowtop strong{font-size:9px}.right{margin-left:auto;font-size:8px;color:#5b646d}.desc{font-size:8px;color:#4f5962;margin-top:4px}
.errorbox{display:none;background:var(--red-soft);border:1px solid #efc2cb;color:var(--red);border-radius:9px;padding:10px;margin-bottom:12px;font-size:9px}.foot{font-size:8px;color:#68717a;padding:16px 0 5px}
@media(max-width:1250px){.kpis{grid-template-columns:repeat(4,1fr)}.metrics{grid-template-columns:repeat(3,1fr)}.three{grid-template-columns:1fr 1fr}}@media(max-width:800px){.hero{flex-direction:column}.two,.three{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(2,1fr)}.metrics{grid-template-columns:repeat(2,1fr)}}

.tv-research-card{margin-top:16px}
.tv-research-grid{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:10px;align-items:start}
.tv-chart-shell{background:#0b1015;border:1px solid #1d2730;border-radius:12px;overflow:hidden;min-width:0;box-shadow:0 12px 30px rgba(15,23,42,.12)}
.tv-chart-toolbar{display:flex;align-items:center;gap:7px;flex-wrap:wrap;padding:10px;border-bottom:1px solid #dfe5eb;background:#f8fafb}
.tv-chart-toolbar input,.tv-chart-toolbar select{border:1px solid #cfd6de;background:#fff;border-radius:8px;padding:7px 9px;font-size:9px;font-weight:800;min-width:100px}
.tv-chart-toolbar input{width:125px;text-transform:uppercase}.tv-chart-canvas{height:560px;width:100%;position:relative;background:#0b1015}
.tv-chart-host{position:absolute;inset:0}
.tv-chart-empty{display:flex;align-items:center;justify-content:center;height:100%;font-size:10px;color:#8f9aa6;padding:20px;text-align:center;background:#0b1015}
.tv-chart-overlay{position:absolute;inset:0;pointer-events:none;z-index:2}
.tv-chart-legend{position:absolute;left:12px;top:10px;display:flex;align-items:center;gap:9px;flex-wrap:wrap;padding:7px 10px;border:1px solid rgba(160,174,192,.18);border-radius:8px;background:rgba(11,16,21,.84);backdrop-filter:blur(7px);box-shadow:0 8px 25px rgba(0,0,0,.16);font-size:8px;color:#cbd4de}
.tv-chart-legend .symbol{font-size:9px;font-weight:900;color:#fff;letter-spacing:.35px}.tv-chart-legend .sep{color:#566270}.tv-chart-legend .kv{font-variant-numeric:tabular-nums}.tv-chart-legend .kv b{color:#fff;font-weight:800}
.tv-chart-regime{position:absolute;right:12px;top:10px;display:flex;align-items:center;gap:6px;padding:6px 8px;border:1px solid rgba(160,174,192,.18);border-radius:999px;background:rgba(11,16,21,.78);color:#9fb0c1;font-size:7px;font-weight:900;letter-spacing:.7px;text-transform:uppercase}
.tv-chart-regime .dot{width:6px;height:6px;border-radius:50%;background:#36c98f;box-shadow:0 0 0 3px rgba(54,201,143,.13)}
.tv-chart-footer{position:absolute;left:12px;right:12px;bottom:9px;display:flex;justify-content:space-between;align-items:center;gap:8px;color:#72808f;font-size:7px;text-transform:uppercase;letter-spacing:.6px}.tv-chart-footer .right{margin-left:auto;color:#94a2b2}.tv-chart-footer strong{color:#c9d3de}
.tv-signal-tooltip{position:absolute;min-width:210px;max-width:280px;padding:9px 10px;border:1px solid rgba(148,163,184,.28);border-radius:9px;background:rgba(7,11,16,.94);backdrop-filter:blur(9px);box-shadow:0 12px 30px rgba(0,0,0,.28);color:#dbe5ef;font-size:8px;line-height:1.45;z-index:5;pointer-events:none}.tv-signal-tooltip .tt-head{font-size:9px;font-weight:900;letter-spacing:.25px;margin-bottom:3px}.tv-signal-tooltip .tt-sub{color:#8ea0b2}.tv-signal-tooltip .tt-grid{display:grid;grid-template-columns:1fr 1fr;gap:4px 9px;margin-top:7px}.tv-signal-tooltip .tt-k{color:#748394;font-size:7px;text-transform:uppercase;letter-spacing:.5px}.tv-signal-tooltip .tt-v{color:#f4f7fa;font-weight:800;font-variant-numeric:tabular-nums}.tv-focus-badge{position:absolute;right:12px;top:43px;padding:6px 9px;border:1px solid rgba(58,166,255,.38);border-radius:8px;background:rgba(7,11,16,.9);color:#bcdcff;font-size:7px;font-weight:900;letter-spacing:.5px;text-transform:uppercase;z-index:4;pointer-events:none;box-shadow:0 8px 20px rgba(0,0,0,.2)}.tv-research-zones{position:absolute;inset:0;z-index:1;pointer-events:none;overflow:hidden}.tv-zone{position:absolute;top:0;bottom:0;border-left:1px solid rgba(112,129,148,.12);border-right:1px solid rgba(112,129,148,.12);background:rgba(100,120,140,.035)}.tv-zone.train{background:rgba(58,166,255,.045);border-color:rgba(58,166,255,.14)}.tv-zone.validation{background:rgba(216,169,74,.05);border-color:rgba(216,169,74,.16)}.tv-zone.independent{background:rgba(54,201,143,.05);border-color:rgba(54,201,143,.16)}.tv-zone-label{position:absolute;top:88px;left:7px;padding:4px 6px;border-radius:5px;background:rgba(7,11,15,.74);border:1px solid rgba(160,174,192,.15);color:#aebaca;font-size:6px;font-weight:900;letter-spacing:.8px;text-transform:uppercase;white-space:nowrap}@media(max-width:800px){.tv-zone-label{display:none}}
.tv-research-meta{display:grid;gap:8px}.tv-research-meta .box{min-height:0}.tv-source-note{font-size:8px;color:var(--muted);line-height:1.5}
.tv-badge{display:inline-flex;align-items:center;border-radius:999px;padding:4px 7px;font-size:8px;font-weight:900;background:var(--blue-soft);color:var(--blue)}
.tv-attribution{padding:7px 10px;font-size:8px;color:var(--muted);border-top:1px solid #dfe5eb;background:#fff}.tv-attribution a{color:#2c69b8;text-decoration:none;font-weight:900}
@media(max-width:1050px){.tv-research-grid{grid-template-columns:1fr}.tv-research-meta{grid-template-columns:repeat(3,1fr)}}
@media(max-width:800px){.tv-research-meta{grid-template-columns:1fr}.tv-chart-canvas{height:460px}.tv-chart-legend{left:7px;right:7px;top:7px}.tv-chart-regime{display:none}.tv-chart-footer{left:7px;right:7px}}
.tv-signal-selected{border-color:#111!important;background:#fff!important;box-shadow:0 8px 24px rgba(17,17,17,.06)}
.tv-provenance-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px}.tv-provenance-item{border:1px solid var(--line);border-radius:7px;background:var(--soft);padding:7px}.tv-provenance-item .k{font-size:7px;text-transform:uppercase;letter-spacing:.6px;font-weight:900;color:#616a73}.tv-provenance-item .v{font-size:8px;color:#111;margin-top:3px;word-break:break-word}.tv-provenance-wide{grid-column:1/-1}@media(max-width:800px){.tv-provenance-grid{grid-template-columns:1fr}}

.decision-cockpit{display:grid;grid-template-columns:1.2fr .8fr;gap:10px}
.cockpit-card{border:1px solid #dfe5eb;border-radius:10px;background:#fff;padding:12px;min-width:0}
.cockpit-card.wide{grid-column:1/-1}
.cockpit-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.cockpit-kpi{border:1px solid #e4e9ee;border-radius:9px;padding:10px;background:linear-gradient(180deg,#fff,#f8fafc)}
.cockpit-kpi .cap{font-size:7px;text-transform:uppercase;letter-spacing:.7px;color:#748394;font-weight:900}
.cockpit-kpi .value{font-size:17px;font-weight:900;margin-top:7px;line-height:1.1;word-break:break-word}
.cockpit-kpi .sub{font-size:7px;color:#8a96a3;margin-top:5px;line-height:1.4}
.cockpit-flow{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin-top:10px}
.cockpit-step{position:relative;border:1px solid #dfe5eb;border-radius:9px;padding:9px;background:#fafbfd;min-height:70px}
.cockpit-step:after{content:'→';position:absolute;right:-9px;top:23px;color:#9aa7b3;font-weight:900}
.cockpit-step:last-child:after{display:none}
.cockpit-step .step-n{font-size:6px;color:#8a96a3;text-transform:uppercase;letter-spacing:.7px;font-weight:900}.cockpit-step .step-v{margin-top:6px;font-size:9px;font-weight:900;color:#24313f}
.cockpit-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.cockpit-note{border:1px solid #e4e9ee;border-radius:8px;padding:10px;background:#fafbfd;font-size:8px;line-height:1.5;color:#556271}.cockpit-note .cap{display:block;margin-bottom:5px;color:#7a8795;font-weight:900;text-transform:uppercase;letter-spacing:.6px;font-size:7px}.cockpit-question{border:1px solid #dfe5eb;border-radius:9px;background:#f7f9fb;padding:12px;font-size:11px;line-height:1.5;font-weight:800;color:#24313f}.cockpit-flag{border-left:3px solid #a9b3bd;padding-left:9px;margin-top:9px;font-size:8px;line-height:1.5;color:#556271}.cockpit-flag.good{border-color:#148a5d}.cockpit-flag.warn{border-color:#b17a13}.cockpit-flag.bad{border-color:#b6314d}
@media(max-width:900px){.decision-cockpit{grid-template-columns:1fr}.cockpit-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.cockpit-flow{grid-template-columns:1fr 1fr}.cockpit-step:after{display:none}.cockpit-grid{grid-template-columns:1fr}}

.validation-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.validation-card{border:1px solid #dfe5eb;border-radius:10px;background:#fff;padding:12px;min-width:0}
.validation-card.wide{grid-column:span 2}
.validation-matrix{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin-top:10px}
.validation-metric{position:relative;border:1px solid #dfe5eb;border-radius:9px;padding:10px;min-height:108px;background:linear-gradient(180deg,#fff,#f8fafc)}
.validation-metric .vm-head{display:flex;align-items:center;justify-content:space-between;gap:8px}
.validation-metric .vm-label{font-size:9px;font-weight:900;letter-spacing:.5px;color:#475569;text-transform:uppercase}
.validation-metric .vm-value{font-size:20px;font-weight:900;margin-top:12px;line-height:1}
.validation-metric .vm-bar{position:absolute;left:10px;right:10px;bottom:11px;height:6px;border-radius:999px;background:#e7edf3;overflow:hidden}
.validation-metric .vm-fill{height:100%;border-radius:999px}
.validation-metric.good .vm-fill{background:#148a5d}.validation-metric.mid .vm-fill{background:#b17a13}.validation-metric.bad .vm-fill{background:#b6314d}.validation-metric.na .vm-fill{background:#9aa7b3}
.validation-metric .vm-note{margin-top:7px;font-size:8px;color:#7a8795;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.validation-stat-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:12px}
.vstat{border:1px solid #e4e9ee;border-radius:8px;padding:9px;background:#fafbfd}.vstat span{display:block;font-size:8px;color:#7a8795}.vstat b{display:block;margin-top:4px;font-size:13px}
.decision-stack{display:grid;gap:7px;margin-top:12px}.decision-row{display:flex;justify-content:space-between;gap:12px;padding:8px 9px;border:1px solid #e4e9ee;border-radius:8px;background:#fafbfd}.decision-row span{font-size:8px;color:#7a8795;text-transform:uppercase;font-weight:800}.decision-row b{font-size:9px;text-align:right}
.validation-note{margin-top:9px;padding:8px 9px;border-radius:8px;background:#f5f7fa;font-size:8px;color:#556271;line-height:1.5}
.question-box{margin-top:12px;border:1px solid #dfe5eb;border-radius:9px;background:#f7f9fb;padding:12px;font-size:11px;line-height:1.5;font-weight:700;color:#24313f}
@media(max-width:900px){.validation-grid{grid-template-columns:1fr}.validation-card.wide{grid-column:span 1}.validation-matrix{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
<script src="https://unpkg.com/lightweight-charts@5.2.0/dist/lightweight-charts.standalone.production.js"></script>
</head>
<body>
<header class="top"><div class="logo">MarketHQ</div><div class="sub">STRATEGY EXPLORER</div><div class="grow"></div><span id="safety" class="pill safe">RESEARCH ONLY</span><span id="schema" class="pill">CHECKING</span><button class="btn" onclick="loadAll()">Yenile</button></header>

<main class="wrap">
<div id="errorBox" class="errorbox"></div>
<section class="hero"><div class="grow"><div class="sub">MARKET RESEARCH OS</div><h1>Strategy Explorer</h1><p>Tek stratejinin performansını, bağımsız kanıtlarını, review kararını ve öğrenme sıralamasını aynı ekranda karşılaştır.</p></div><div class="actions"><button class="btn" onclick="focusId('strategy')">Strategy</button><button class="btn" onclick="focusId('symbols')">Symbols</button><button class="btn" onclick="focusId('evidence')">Evidence</button><button class="btn" onclick="focusId('learning')">Learning</button></div></section>

<nav class="nav"><a href="#strategy">Strategy</a><a href="#decision-cockpit">Decision Cockpit</a><a href="#validation">Validation</a><a href="#charts">Charts</a><a href="#tradingview">TradingView</a><a href="#trades">Trade Viewer</a><a href="#symbols">Symbols</a><a href="#evidence">Evidence</a><a href="#brain">Brain</a><a href="#learning">Learning</a><a href="#database">Database</a></nav>

<section class="kpis">
<div class="kpi"><div class="label">Brain Nodes</div><div id="kNodes" class="value">—</div></div><div class="kpi"><div class="label">Brain Edges</div><div id="kEdges" class="value">—</div></div><div class="kpi"><div class="label">Episodes</div><div id="kEpisodes" class="value">—</div></div><div class="kpi"><div class="label">Claims</div><div id="kClaims" class="value">—</div></div><div class="kpi"><div class="label">Learning Events</div><div id="kEvents" class="value">—</div></div><div class="kpi"><div class="label">Active Queue</div><div id="kQueue" class="value">—</div></div><div class="kpi"><div class="label">Knowledge</div><div id="kKnowledge" class="value">—</div></div><div class="kpi"><div class="label">Learned Rules</div><div id="kRules" class="value">—</div></div>
</section>

<section id="strategy" class="card"><div class="head"><h2>Strategy Intelligence</h2><span id="strategyId" class="muted">—</span><div class="grow"></div><span id="verdictTag" class="tag">—</span></div><div class="body">
<div class="two"><div class="box"><div class="cap">Strategy</div><div id="strategyName" class="big">—</div><div id="strategyClass" class="small">—</div></div><div class="box"><div class="cap">Final Research Decision</div><div id="decision" class="big">—</div><div id="decisionAction" class="small">—</div></div></div>
<div class="metrics" style="margin-top:10px"><div class="metric"><div class="cap">V6 Score</div><div id="v6" class="n">—</div></div><div class="metric"><div class="cap">Cross Symbol</div><div id="cross" class="n">—</div></div><div class="metric"><div class="cap">Cost</div><div id="cost" class="n">—</div></div><div class="metric"><div class="cap">Parameter</div><div id="param" class="n">—</div></div><div class="metric"><div class="cap">Regime</div><div id="regime" class="n">—</div></div><div class="metric"><div class="cap">WFO</div><div id="wfo" class="n">—</div></div></div>
<div class="question box" style="margin-top:10px"><div class="cap">Next Research Question</div><div id="nextQuestion" class="small">—</div></div>
</div></section>

<section id="decision-cockpit" class="card">
<div class="head"><h2>Research Decision Cockpit</h2><span id="cockpitMeta" class="muted">Decision lineage · evidence · next action</span><div class="grow"></div><span id="cockpitTag" class="tag">—</span></div>
<div class="body">
  <div class="decision-cockpit">
    <div class="cockpit-card wide">
      <div class="cockpit-kpis">
        <div class="cockpit-kpi"><div class="cap">Final Decision</div><div id="cockpitDecision" class="value">—</div><div id="cockpitDecisionSub" class="sub">—</div></div>
        <div class="cockpit-kpi"><div class="cap">Research Action</div><div id="cockpitAction" class="value">—</div><div id="cockpitActionSub" class="sub">—</div></div>
        <div class="cockpit-kpi"><div class="cap">Review</div><div id="cockpitReview" class="value">—</div><div id="cockpitReviewSub" class="sub">—</div></div>
        <div class="cockpit-kpi"><div class="cap">Evidence</div><div id="cockpitEvidence" class="value">—</div><div id="cockpitEvidenceSub" class="sub">—</div></div>
      </div>
      <div class="cockpit-flow">
        <div class="cockpit-step"><div class="step-n">01 · Review</div><div id="cockpitFlowReview" class="step-v">—</div></div>
        <div class="cockpit-step"><div class="step-n">02 · Robustness</div><div id="cockpitFlowRobustness" class="step-v">—</div></div>
        <div class="cockpit-step"><div class="step-n">03 · Evidence</div><div id="cockpitFlowEvidence" class="step-v">—</div></div>
        <div class="cockpit-step"><div class="step-n">04 · Decision</div><div id="cockpitFlowDecision" class="step-v">—</div></div>
        <div class="cockpit-step"><div class="step-n">05 · Next</div><div id="cockpitFlowNext" class="step-v">—</div></div>
      </div>
    </div>
    <div class="cockpit-card">
      <div class="chart-title">Evidence Posture</div><div class="chart-subtitle">What the current snapshot actually proves</div>
      <div class="cockpit-note"><span class="cap">Verification</span><span id="cockpitVerification">—</span></div>
      <div class="cockpit-note" style="margin-top:8px"><span class="cap">Cross-time consistency</span><span id="cockpitConsistency">—</span></div>
      <div id="cockpitEvidenceFlag" class="cockpit-flag">—</div>
    </div>
    <div class="cockpit-card">
      <div class="chart-title">Research Quality Snapshot</div><div class="chart-subtitle">Available robustness evidence · no unavailable metric is guessed</div>
      <div class="cockpit-grid">
        <div class="cockpit-note"><span class="cap">WFO Positive</span><span id="cockpitWfo">—</span></div>
        <div class="cockpit-note"><span class="cap">Cross Symbol</span><span id="cockpitCross">—</span></div>
        <div class="cockpit-note"><span class="cap">Cost Survival</span><span id="cockpitCost">—</span></div>
        <div class="cockpit-note"><span class="cap">Parameter Stability</span><span id="cockpitParam">—</span></div>
        <div class="cockpit-note"><span class="cap">Regime Stability</span><span id="cockpitRegime">—</span></div>
        <div class="cockpit-note"><span class="cap">Holdout</span><span id="cockpitHoldout">—</span></div>
      </div>
    </div>
    <div class="cockpit-card wide">
      <div class="chart-title">Why This Decision?</div><div class="chart-subtitle">Decision context assembled from the existing review, consolidation and learning records</div>
      <div id="cockpitWhy" class="cockpit-note">—</div>
      <div class="chart-title" style="margin-top:12px">Next Research Question</div>
      <div id="cockpitQuestion" class="cockpit-question">—</div>
    </div>
  </div>
</div>
</section>

<section id="validation" class="card">
<div class="head">
  <h2>Validation &amp; Robustness Board</h2>
  <span id="validationMeta" class="muted">—</span>
  <div class="grow"></div>
  <span id="validationGate" class="tag">—</span>
</div>
<div class="body">
  <div class="validation-grid">
    <div class="validation-card wide">
      <div class="chart-card-head"><div><div class="chart-title">Research Robustness Matrix</div><div class="chart-subtitle">Existing pipeline evidence · no new claims are inferred when a metric is unavailable</div></div><div id="validationMatrixMeta" class="chart-mini-meta">—</div></div>
      <div id="validationMatrix" class="validation-matrix"></div>
    </div>
    <div class="validation-card">
      <div class="chart-title">Evidence Coverage</div>
      <div class="chart-subtitle">Consolidated symbol/time evidence</div>
      <div class="validation-stat-grid">
        <div class="vstat"><span>Evidence records</span><b id="valEvidenceRecords">—</b></div>
        <div class="vstat"><span>Symbol runs</span><b id="valSymbolRuns">—</b></div>
        <div class="vstat"><span>Positive runs</span><b id="valPositiveRuns">—</b></div>
        <div class="vstat"><span>Negative runs</span><b id="valNegativeRuns">—</b></div>
        <div class="vstat"><span>Pooled positive</span><b id="valPooledPositive">—</b></div>
        <div class="vstat"><span>Holdout</span><b id="valHoldout">—</b></div>
      </div>
    </div>
    <div class="validation-card">
      <div class="chart-title">Decision Gate</div>
      <div class="chart-subtitle">Review → final decision → next action</div>
      <div class="decision-stack">
        <div class="decision-row"><span>Review</span><b id="valReviewVerdict">—</b></div>
        <div class="decision-row"><span>Review score</span><b id="valReviewScore">—</b></div>
        <div class="decision-row"><span>Final decision</span><b id="valFinalDecision">—</b></div>
        <div class="decision-row"><span>Action</span><b id="valDecisionAction">—</b></div>
      </div>
      <div class="validation-note" id="valVerification">—</div>
    </div>
    <div class="validation-card wide">
      <div class="chart-title">Research Continuation</div>
      <div class="chart-subtitle">The next question remains part of the research lineage</div>
      <div class="question-box" id="validationNextQuestion">—</div>
    </div>
  </div>
</div>
</section>

<section id="charts" class="card">
<div class="head">
  <h2>Performance Charts</h2>
  <span id="chartMeta" class="muted">—</span>
  <div class="grow"></div>
  <div id="sourceButtons" class="chart-buttons"></div>
</div>
<div class="body">
  <div class="chart-grid">
    <div class="chart-card">
      <div class="chart-title">Return by Symbol</div>
      <div class="chart-subtitle">Selected evidence source</div>
      <div id="returnChart" class="svg-wrap"></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">Profit Factor by Symbol</div>
      <div class="chart-subtitle">PF &gt; 1 is shown above the neutral line</div>
      <div id="pfChart" class="svg-wrap"></div>
    </div>
    <div class="chart-card wide">
      <div class="chart-title">Risk / Return Map</div>
      <div class="chart-subtitle">X = Max Drawdown · Y = Return</div>
      <div id="scatterChart" class="svg-wrap tall"></div>
    </div>
    <div class="chart-card wide">
      <div class="chart-title">Trade PnL Curve</div>
      <div class="chart-subtitle">Selected trade dataset · cumulative net PnL · point'e tıklayarak trade seç</div>
      <div id="tradePnlChart" class="svg-wrap tall"></div>
    </div>
    <div class="chart-card wide">
      <div class="chart-card-head"><div><div class="chart-title">Drawdown / Underwater</div><div class="chart-subtitle">Cumulative net PnL peak-to-trough distance · depth and recovery context</div></div><div id="drawdownMeta" class="chart-mini-meta">—</div></div>
      <div id="drawdownChart" class="svg-wrap tall"></div>
    </div>
    <div class="chart-card">
      <div class="chart-card-head"><div><div class="chart-title">Rolling Trade Sharpe</div><div class="chart-subtitle">Rolling risk-adjusted quality · trade-level window</div></div><div id="rollingSharpeMeta" class="chart-mini-meta">window 10</div></div>
      <div class="chart-inline-controls"><button class="chart-button active" data-rs-window="10" onclick="setRollingSharpeWindow(10,this)">10</button><button class="chart-button" data-rs-window="20" onclick="setRollingSharpeWindow(20,this)">20</button><button class="chart-button" data-rs-window="30" onclick="setRollingSharpeWindow(30,this)">30</button></div>
      <div id="rollingSharpeChart" class="svg-wrap"></div>
    </div>
    <div class="chart-card">
      <div class="chart-card-head"><div><div class="chart-title">Trade Return Distribution</div><div class="chart-subtitle">Net PnL distribution by trade · central tendency and hit quality</div></div><div id="distributionMeta" class="chart-mini-meta">—</div></div>
      <div id="distributionChart" class="svg-wrap"></div>
    </div>
  </div>
</div>
</section>



<section id="regime" class="card">
<div class="head">
  <h2>Regime &amp; Stress Lab</h2>
  <span id="regimeMeta" class="muted">Research-only analytics · heuristic regime classification</span>
  <div class="grow"></div>
  <div class="chart-buttons">
    <button class="chart-button active" data-stress-bps="0" onclick="setStressBps(0,this)">0 bps</button>
    <button class="chart-button" data-stress-bps="5" onclick="setStressBps(5,this)">5 bps</button>
    <button class="chart-button" data-stress-bps="10" onclick="setStressBps(10,this)">10 bps</button>
    <button class="chart-button" data-stress-bps="20" onclick="setStressBps(20,this)">20 bps</button>
  </div>
</div>
<div class="body">
  <div class="regime-grid">
    <div class="chart-card wide">
      <div class="chart-card-head"><div><div class="chart-title">Market Regime Timeline</div><div class="chart-subtitle">EMA relationship + 20-bar realized volatility · heuristic labels for research exploration</div></div><div id="regimeTimelineMeta" class="chart-mini-meta">—</div></div>
      <div id="regimeTimeline" class="regime-timeline"></div>
    </div>
    <div class="chart-card">
      <div class="chart-card-head"><div><div class="chart-title">Performance by Regime</div><div class="chart-subtitle">Trade PnL grouped by regime at entry</div></div><div id="regimePerfMeta" class="chart-mini-meta">—</div></div>
      <div id="regimePerformance" class="regime-table"></div>
    </div>
    <div class="chart-card">
      <div class="chart-card-head"><div><div class="chart-title">Cost Stress</div><div class="chart-subtitle">Hypothetical round-trip friction applied to each trade</div></div><div id="stressMeta" class="chart-mini-meta">0 bps</div></div>
      <div id="stressPanel" class="stress-panel"></div>
    </div>
    <div class="chart-card wide">
      <div class="chart-card-head"><div><div class="chart-title">Drawdown Duration</div><div class="chart-subtitle">Consecutive trades spent below the prior equity peak</div></div><div id="ddDurationMeta" class="chart-mini-meta">—</div></div>
      <div id="ddDurationChart" class="svg-wrap"></div>
    </div>
  </div>
  <div class="research-footnote">Regime labels and cost-stress outputs are analytical heuristics calculated in the browser from the loaded research data; they do not modify Research Memory, place orders, or represent execution assumptions from a broker.</div>
</div>
</section>

<section id="diagnostics" class="card">
<div class="head"><h2>Sequence &amp; Trade Diagnostics</h2><span id="diagnosticsMeta" class="muted">Research-only sequence analysis · no database writes</span></div>
<div class="body">
  <div class="diagnostics-grid">
    <div class="diagnostic-card">
      <div class="chart-card-head"><div><div class="chart-title">Monte Carlo Outcome Envelope</div><div class="chart-subtitle">Bootstrap resampling of observed trade PnL · sequence-risk / ending-equity uncertainty</div></div><div id="mcMeta" class="chart-mini-meta">250 paths</div></div>
      <div class="diag-kpis"><div class="diag-kpi"><div class="cap">P5 Final</div><div id="mcP5" class="n">—</div></div><div class="diag-kpi"><div class="cap">Median Final</div><div id="mcP50" class="n">—</div></div><div class="diag-kpi"><div class="cap">P95 Final</div><div id="mcP95" class="n">—</div></div><div class="diag-kpi"><div class="cap">Prob. Positive</div><div id="mcProb" class="n">—</div></div></div>
      <div id="monteCarloChart" class="diag-chart"></div>
      <div class="diag-note">Monte Carlo burada gözlenen trade PnL'lerinin replacement ile yeniden örneklenmesiyle hesaplanır. Gerçekleşmiş gelecek yolu veya broker/execution tahmini değildir.</div>
    </div>
    <div class="diagnostic-card">
      <div class="chart-card-head"><div><div class="chart-title">MAE / MFE Trade Map</div><div class="chart-subtitle">Holding window içindeki adverse/favorable excursion · entry referanslı</div></div><div id="maeMfeMeta" class="chart-mini-meta">—</div></div>
      <div class="diag-kpis"><div class="diag-kpi"><div class="cap">Median MAE</div><div id="maeMedian" class="n">—</div></div><div class="diag-kpi"><div class="cap">Median MFE</div><div id="mfeMedian" class="n">—</div></div><div class="diag-kpi"><div class="cap">Best MFE</div><div id="mfeBest" class="n">—</div></div><div class="diag-kpi"><div class="cap">Worst MAE</div><div id="maeWorst" class="n">—</div></div></div>
      <div id="maeMfeChart" class="diag-chart"></div>
      <div class="diag-note">MAE negatif (zarar yönü), MFE pozitif (favorable excursion) gösterilir. OHLCV dönemi yüklenmemişse harita hesaplanamaz.</div>
    </div>
    <div class="diagnostic-card">
      <div class="chart-card-head"><div><div class="chart-title">Win / Loss Streak Analysis</div><div class="chart-subtitle">Trade sıralamasındaki ardışık kazanç/kayıp kümeleri</div></div><div id="streakMeta" class="chart-mini-meta">—</div></div>
      <div class="streak-grid"><div class="streak-box"><div class="cap">Longest Win Streak</div><div id="longWin" class="big">—</div></div><div class="streak-box"><div class="cap">Longest Loss Streak</div><div id="longLoss" class="big">—</div></div><div class="streak-box"><div class="cap">Current Streak</div><div id="currentStreak" class="big">—</div></div><div class="streak-box"><div class="cap">Avg Abs. Streak</div><div id="avgStreak" class="big">—</div></div></div>
      <div id="streakBars" class="streak-bars"></div>
    </div>
  </div>
  <div class="diag-foot">Bu bölüm yalnızca yüklenmiş trade/OHLCV verisini analiz eder; Research Memory yazmaz, broker execution yapmaz ve gelecekteki getiriyi garanti etmez.</div>
</div>
</section>

<section id="tradingview" class="card tv-research-card">
<div class="head">
  <h2>TradingView Research Chart</h2>
  <span id="tvChartMeta" class="muted">—</span>
  <div class="grow"></div>
  <span id="tvChartSafety" class="tv-badge">RESEARCH ONLY</span>
</div>
<div class="body">
  <div class="tv-research-grid">
    <div class="tv-chart-shell">
      <div class="tv-chart-toolbar">
        <input id="tvSymbol" value="THYAO.IS" placeholder="THYAO.IS" aria-label="Sembol">
        <select id="tvInterval" aria-label="Zaman aralığı"><option value="1d" selected>1D</option></select>
        <select id="tvLimit" aria-label="Bar sayısı"><option value="250">250 bars</option><option value="500" selected>500 bars</option><option value="1000">1000 bars</option><option value="5000">5000 bars</option></select>
        <button class="chart-button active" onclick="loadTradingViewResearchChart()">LOAD</button>
        <button class="chart-button" onclick="fitTradingViewResearchChart()">FIT</button>
        <button id="tvEmaToggle" class="chart-button active" onclick="toggleTvEma(this)">EMA ON</button>
        <button id="tvSignalToggle" class="chart-button active" onclick="toggleTvSignals(this)">SIGNALS ON</button>
        <button id="tvZoneToggle" class="chart-button active" onclick="toggleTvResearchZones(this)">RESEARCH ZONES ON</button>
        <button id="tvPathToggle" class="chart-button active" onclick="toggleTvTradePath(this)">TRADE PATH ON</button>
        <button class="chart-button" onclick="useSelectedTradeInTvChart()">USE SELECTED TRADE</button>
        <span id="tvChartStatus" class="trade-filter-note">—</span>
      </div>
      <div class="tv-chart-canvas">
        <div id="tvResearchChart" class="tv-chart-host"><div class="tv-chart-empty">TradingView Research Chart hazırlanıyor…</div></div>
        <div id="tvResearchZones" class="tv-research-zones" aria-hidden="true"></div>
        <div class="tv-chart-overlay" aria-hidden="true">
          <div class="tv-chart-legend">
            <span id="tvLegendSymbol" class="symbol">THYAO.IS · 1D</span>
            <span class="sep">•</span><span id="tvLegendTime" class="kv">—</span>
            <span class="sep">•</span><span class="kv">O <b id="tvLegendOpen">—</b></span>
            <span class="kv">H <b id="tvLegendHigh">—</b></span>
            <span class="kv">L <b id="tvLegendLow">—</b></span>
            <span class="kv">C <b id="tvLegendClose">—</b></span>
            <span class="kv">V <b id="tvLegendVolume">—</b></span>
            <span class="kv">EMA20 <b id="tvLegendEma20">—</b></span>
            <span class="kv">EMA50 <b id="tvLegendEma50">—</b></span>
          </div>
          <div class="tv-chart-regime"><span class="dot"></span><span>Research / Read Only</span></div>
          <div id="tvSignalTooltip" class="tv-signal-tooltip" hidden></div>
          <div id="tvFocusBadge" class="tv-focus-badge" hidden></div>
          <div class="tv-chart-footer"><span>MarketHQ Research Terminal <strong>·</strong> historical OHLCV</span><span id="tvLegendSelected" class="right">No selection</span></div>
        </div>
      </div>
      <div class="tv-attribution">Powered by <a href="https://www.tradingview.com/" target="_blank" rel="noopener nofollow">TradingView</a> Lightweight Charts™ · MarketHQ research visualization</div>
    </div>
    <div class="tv-research-meta">
      <div class="box"><div class="cap">Symbol</div><div id="tvInfoSymbol" class="big">THYAO.IS</div><div id="tvInfoRange" class="small">—</div></div>
      <div class="box"><div class="cap">Data Source</div><div id="tvInfoSource" class="big">—</div><div id="tvInfoBars" class="small">—</div></div>
      <div class="box"><div class="cap">Research Decision</div><div id="tvInfoDecision" class="big">—</div><div id="tvInfoDecisionAction" class="small">—</div></div>
      <div class="box"><div class="cap">Strategy / Experiment</div><div id="tvInfoStrategy" class="big">—</div><div id="tvInfoExperiment" class="small">—</div></div>
      <div class="box"><div class="cap">Next Research Question</div><div id="tvInfoQuestion" class="small">—</div></div>
      <div class="box"><div class="cap">Selected Trade</div><div id="tvInfoTrade" class="small">Trade Viewer'dan bir işlem seçerek aynı sembolü grafiğe taşıyabilirsin.</div></div>
      <div class="box"><div class="cap">Research Signals</div><div id="tvInfoSignals" class="small">Sinyal eventleri yükleniyor…</div></div>
      <div class="box"><div class="cap">Selected Signal</div><div id="tvSelectedSignalTitle" class="big">None</div><div id="tvSelectedSignal" class="small">Grafikte bir BUY/EXIT işaretine tıklayın.</div></div>
      <div class="box"><div class="cap">Research Provenance</div><div id="tvProvenance" class="small">Bir sinyal seçildiğinde experiment → result → validation → decision zinciri burada gösterilir.</div></div>
      <div class="box"><div class="cap">Research Role</div><div class="small">Grafik yalnızca araştırma/kanıt görselleştirmesidir. Emir göndermez, broker execution yapmaz ve mevcut Research Loop'a yazmaz.</div></div>
    </div>
  </div>
</div>
</section>

<section id="trades" class="card">
<div class="head">
  <h2>Trade Viewer V3.1</h2>
  <span id="tradeMeta" class="muted">—</span>
  <div class="grow"></div>
  <select id="tradeDataset" class="trade-select" onchange="renderTradeControls();renderSelectedTrades()"></select>
  <select id="tradeSymbol" class="trade-select" onchange="renderSelectedTrades()"></select>
  <select id="tradeOutcome" class="trade-select" onchange="renderSelectedTrades()">
    <option value="ALL">ALL</option>
    <option value="WIN">WIN</option>
    <option value="LOSS">LOSS</option>
  </select>
  <select id="tradeSide" class="trade-select" onchange="renderSelectedTrades()">
    <option value="ALL">ALL SIDES</option>
    <option value="LONG">LONG</option>
    <option value="SHORT">SHORT</option>
  </select>
  <select id="tradeIndicator" class="trade-select" onchange="renderTradeChartForSelected()">
    <option value="EMA">EMA 20/50</option>
    <option value="NONE">NO INDICATOR</option>
  </select>
</div>
<div class="body">
  <div class="metrics trade-metrics">
    <div class="metric"><div class="cap">Trades</div><div id="tradeCount" class="n">—</div></div>
    <div class="metric"><div class="cap">Wins</div><div id="tradeWins" class="n">—</div></div>
    <div class="metric"><div class="cap">Losses</div><div id="tradeLosses" class="n">—</div></div>
    <div class="metric"><div class="cap">Win Rate</div><div id="tradeWinRate" class="n">—</div></div>
    <div class="metric"><div class="cap">Net PnL</div><div id="tradeNetPnl" class="n">—</div></div>
    <div class="metric"><div class="cap">Avg Return</div><div id="tradeAvgReturn" class="n">—</div></div>
  </div>
  <div class="tablewrap" style="margin-top:12px">
    <table>
      <thead>
        <tr>
          <th>#</th><th>Side</th><th>Entry Time</th><th>Exit Time</th>
          <th>Entry</th><th>Exit</th><th>SL</th><th>TP</th>
          <th>Net PnL</th><th>Return</th><th>Bars</th><th>Exit Reason</th>
        </tr>
      </thead>
      <tbody id="tradeTable"></tbody>
    </table>
  </div>

  <div class="box trade-chart-box">
    <div class="cap">Selected Trade Chart</div>
    <div class="small">Gerçek tarihsel OHLCV + EMA20/EMA50. Grafik seçilen işlemin giriş/çıkış bölgesine otomatik yakınlaşır.</div>
    <div class="trade-toolbar">
      <span class="cap" style="margin-right:2px">VIEW</span>
      <button id="tradeViewFit" class="chart-button active" onclick="setTradeViewMode('FIT')">FIT TRADE</button>
      <button id="tradeViewFull" class="chart-button" onclick="setTradeViewMode('FULL')">FULL WINDOW</button>
      <button class="chart-button" onclick="renderTradeChartForSelected()">REFRESH CHART</button>
      <span id="tradeChartStatus" class="trade-filter-note">—</span>
    </div>
    <div id="tradeSummary" class="trade-summary"></div>
    <div id="tradeLevels" class="trade-levels"></div>
    <div id="tradePriceMap" class="trade-chart"></div>
  </div>

  <div class="trade-detail-grid">
    <div class="box">
      <div class="cap">Selected Trade</div>
      <div id="selectedTradeTitle" class="big">None</div>
      <div id="selectedTradeMeta" class="small">Tablodan bir trade satırına tıklayın.</div>
    </div>
    <div class="box">
      <div class="cap">Entry Context</div>
      <div id="selectedEntryContext" class="small">—</div>
    </div>
    <div class="box">
      <div class="cap">Execution</div>
      <div id="selectedExecutionContext" class="small">—</div>
    </div>
  </div>
</div>
</section>

<section id="symbols" class="card"><div class="head"><h2>Symbol Explorer</h2><span id="symbolMeta" class="muted">—</span></div><div class="body">
<div class="metrics"><div class="metric"><div class="cap">V6 Records</div><div id="v6Count" class="n">—</div></div><div class="metric"><div class="cap">Old Independent</div><div id="oldCount" class="n">—</div></div><div class="metric"><div class="cap">Fresh Independent</div><div id="freshCount" class="n">—</div></div><div class="metric"><div class="cap">Unique Symbols</div><div id="uniqueCount" class="n">—</div></div><div class="metric"><div class="cap">Positive Known</div><div id="positiveKnown" class="n">—</div></div><div class="metric"><div class="cap">Negative Known</div><div id="negativeKnown" class="n">—</div></div></div>
<div class="tablewrap" style="margin-top:12px"><table><thead><tr><th>Source</th><th>Symbol</th><th>Return %</th><th>PF</th><th>Trades</th><th>Win Rate</th><th>Max DD</th><th>Status</th></tr></thead><tbody id="symbolTable"></tbody></table></div>
</div></section>

<section id="evidence" class="two">
<div class="card"><div class="head"><h2>Evidence Consolidation</h2><span id="consStatus" class="muted">—</span></div><div class="body">
<div class="metrics" style="grid-template-columns:repeat(4,1fr)"><div class="metric"><div class="cap">Records</div><div id="eRecords" class="n">—</div></div><div class="metric"><div class="cap">Runs</div><div id="eRuns" class="n">—</div></div><div class="metric"><div class="cap">Positive</div><div id="ePos" class="n">—</div></div><div class="metric"><div class="cap">Negative</div><div id="eNeg" class="n">—</div></div></div>
<div class="two" style="margin-top:9px"><div class="box"><div class="cap">Pooled Positive</div><div id="pooled" class="big">—</div></div><div class="box"><div class="cap">Holdout</div><div id="holdout" class="big">—</div></div></div>
<div class="box" style="margin-top:9px"><div class="cap">Interpretation</div><div id="interpretation" class="small">—</div></div>
</div></div>

<div class="card"><div class="head"><h2>Strategy Evidence Review</h2><span id="reviewMethod" class="muted">—</span></div><div class="body">
<div class="box"><div class="cap">Verdict</div><div id="reviewVerdict" class="big">—</div><div id="reviewScore" class="small">—</div></div>
<div class="box" style="margin-top:9px"><div class="cap">Review Reasoning</div><div id="reviewReasoning" class="small">—</div></div>
</div></div>
</section>

<section id="brain" class="card"><div class="head"><h2>Brain</h2><span class="muted">Recent strategy reviews and research queue</span></div><div class="body"><div class="two"><div><div class="sub" style="margin-bottom:6px">Strategy Reviews</div><div id="strategyReviews" class="list"></div></div><div><div class="sub" style="margin-bottom:6px">Research Queue</div><div id="researchQueue" class="list"></div></div></div></div></section>

<section id="learning" class="card"><div class="head"><h2>Learning Ranking</h2><span id="learningMeta" class="muted">—</span></div><div class="body"><div class="tablewrap"><table><thead><tr><th>Strategy</th><th>Learning Score</th><th>Action</th><th>Verification</th><th>Candidate</th><th>Reason</th></tr></thead><tbody id="learningTable"></tbody></table></div></div></section>

<section id="database" class="card"><div class="head"><h2>Database / Schema</h2><span id="dbMeta" class="muted">—</span></div><div class="body"><div class="box"><div class="cap">Freeze</div><div id="freeze" class="big">—</div><div id="freezeHash" class="small">—</div></div></div></section>

<div class="foot">MarketHQ Strategy Explorer V4 → Dashboard Backend V2.3. Research/karar destek ekranıdır; canlı işlem veya broker execution içermez.</div>
</main>

<script>
const $=id=>document.getElementById(id);
const esc=v=>String(v??"").replace(/[&<>"']/g,s=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[s]));
const num=v=>Number(v??0).toLocaleString("tr-TR");
const pct=v=>v==null?"—":(Number(v)*100).toFixed(2)+"%";
const n2=v=>v==null?"—":Number(v).toFixed(2);
const short=(v,n=180)=>{const s=String(v??"");return s.length>n?s.slice(0,n-1)+"…":s};
async function get(path){const r=await fetch(path,{cache:"no-store"});const d=await r.json();if(!r.ok)throw new Error(d.error||"API hatası");return d}
function focusId(id){$(id)?.scrollIntoView({behavior:"smooth"})}


let chartSource = "INDEPENDENT_FRESH";
window.__explorer = {};

function availableChartSources(ex){
  return [...new Set((ex?.datasets || []).map(x => x.source))];
}

function getChartRecords(ex){
  const ds = (ex?.datasets || []).find(x => x.source === chartSource);
  return (ds?.records || []).slice().filter(x => x && x.symbol);
}

function sourceLabel(source){
  if(source === "V6_PIPELINE") return "V6";
  if(source === "INDEPENDENT_OLD") return "OLD";
  if(source === "INDEPENDENT_FRESH") return "FRESH";
  return source || "SOURCE";
}

function svgEscape(v){
  return String(v ?? "").replace(/[&<>"']/g, s => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[s]));
}

function buildBarSvg(records, valueKey, unit){
  const usable = records.filter(x => x[valueKey] != null).slice(0, 20);
  if(!usable.length) return '<div class="muted" style="padding:20px">Bu kaynak için yeterli grafik verisi yok.</div>';

  const W = Math.max(900, usable.length * 55);
  const H = 280, left = 58, right = 20, top = 18, bottom = 74;
  const vals = usable.map(x => Number(x[valueKey]));
  const min = Math.min(0, ...vals);
  const max = Math.max(0, ...vals);
  const span = (max - min) || 1;
  const y = v => top + (max - v) / span * (H - top - bottom);
  const zero = y(0);
  const innerW = W - left - right;
  const bw = innerW / usable.length * .65;

  let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none">`;
  for(let i=0;i<=5;i++){
    const v = min + span * i / 5;
    const yy = y(v);
    svg += `<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" class="chart-gridline"/>`;
    svg += `<text x="${left-8}" y="${yy+3}" text-anchor="end" class="chart-label">${v.toFixed(1)}${unit}</text>`;
  }
  svg += `<line x1="${left}" y1="${zero}" x2="${W-right}" y2="${zero}" class="chart-zero"/>`;

  usable.forEach((r,i)=>{
    const v = Number(r[valueKey]), x = left + (i+.5)*(innerW/usable.length);
    const yy = v >= 0 ? y(v) : zero, hh = Math.max(1, Math.abs(y(v)-zero));
    const fill = v >= 0 ? "#148a5d" : "#b6314d";
    svg += `<rect x="${x-bw/2}" y="${yy}" width="${bw}" height="${hh}" rx="3" fill="${fill}" opacity=".82"/>`;
    svg += `<text x="${x}" y="${H-48}" text-anchor="end" transform="rotate(-45 ${x} ${H-48})" class="chart-label">${svgEscape(r.symbol)}</text>`;
    svg += `<text x="${x}" y="${Math.max(12,yy-4)}" text-anchor="middle" class="chart-value">${v.toFixed(2)}${unit}</text>`;
  });
  return svg + "</svg>";
}

function buildPfSvg(records){
  const usable = records.filter(x => x.profit_factor != null).slice(0, 20);
  if(!usable.length) return '<div class="muted" style="padding:20px">Bu kaynak için PF verisi yok.</div>';

  const W = Math.max(900, usable.length * 55);
  const H = 280, left = 58, right = 20, top = 18, bottom = 74;
  const vals = usable.map(x => Number(x.profit_factor));
  const max = Math.max(2, Math.ceil(Math.max(...vals) * 10) / 10);
  const y = v => top + (max-v)/max*(H-top-bottom);
  const neutral = y(1), innerW = W-left-right, bw = innerW/usable.length*.65;

  let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none">`;
  for(let i=0;i<=5;i++){
    const v=max*i/5, yy=y(v);
    svg += `<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" class="chart-gridline"/>`;
    svg += `<text x="${left-8}" y="${yy+3}" text-anchor="end" class="chart-label">${v.toFixed(1)}</text>`;
  }
  svg += `<line x1="${left}" y1="${neutral}" x2="${W-right}" y2="${neutral}" class="chart-zero"/>`;

  usable.forEach((r,i)=>{
    const v=Number(r.profit_factor), x=left+(i+.5)*(innerW/usable.length), yy=y(v), hh=Math.max(1,neutral-yy);
    const fill=v>=1 ? "#148a5d" : "#b6314d";
    svg += `<rect x="${x-bw/2}" y="${yy}" width="${bw}" height="${hh}" rx="3" fill="${fill}" opacity=".82"/>`;
    svg += `<text x="${x}" y="${H-48}" text-anchor="end" transform="rotate(-45 ${x} ${H-48})" class="chart-label">${svgEscape(r.symbol)}</text>`;
    svg += `<text x="${x}" y="${Math.max(12,yy-4)}" text-anchor="middle" class="chart-value">${v.toFixed(2)}</text>`;
  });
  return svg + "</svg>";
}

function buildScatterSvg(records){
  const usable=records.filter(x=>x.return_percent!=null&&x.max_drawdown_percent!=null).slice(0,30);
  if(!usable.length) return '<div class="muted" style="padding:20px">Risk/return için yeterli veri yok.</div>';
  const W=1000,H=320,left=62,right=25,top=20,bottom=42;
  const xs=usable.map(x=>Number(x.max_drawdown_percent)),ys=usable.map(x=>Number(x.return_percent));
  const xmin=0,xmax=Math.max(1,Math.ceil(Math.max(...xs)*1.15*10)/10);
  const ymin=Math.min(-1,...ys),ymax=Math.max(1,Math.ceil(Math.max(...ys)*1.15*10)/10);
  const xspan=xmax-xmin||1,yspan=ymax-ymin||1;
  const X=v=>left+(v-xmin)/xspan*(W-left-right),Y=v=>top+(ymax-v)/yspan*(H-top-bottom);

  let svg=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
  for(let i=0;i<=5;i++){
    const xv=xmin+xspan*i/5,xx=X(xv),yv=ymin+yspan*i/5,yy=Y(yv);
    svg+=`<line x1="${xx}" y1="${top}" x2="${xx}" y2="${H-bottom}" class="chart-gridline"/>`;
    svg+=`<text x="${xx}" y="${H-20}" text-anchor="middle" class="chart-label">${xv.toFixed(1)}%</text>`;
    svg+=`<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" class="chart-gridline"/>`;
    svg+=`<text x="${left-8}" y="${yy+3}" text-anchor="end" class="chart-label">${yv.toFixed(1)}%</text>`;
  }
  if(ymin<=0&&ymax>=0) svg+=`<line x1="${left}" y1="${Y(0)}" x2="${W-right}" y2="${Y(0)}" class="chart-zero"/>`;
  usable.forEach(r=>{
    const ret=Number(r.return_percent),dd=Number(r.max_drawdown_percent);
    const good=ret>=0;
    svg+=`<circle cx="${X(dd)}" cy="${Y(ret)}" r="5.5" fill="${good?"#148a5d":"#b6314d"}" opacity=".88"><title>${svgEscape(r.symbol)} | Return ${ret.toFixed(2)}% | DD ${dd.toFixed(2)}%</title></circle>`;
  });
  svg+=`<text x="${W/2}" y="${H-4}" text-anchor="middle" class="chart-label">Max Drawdown %</text>`;
  svg+=`<text x="12" y="${H/2}" transform="rotate(-90 12 ${H/2})" text-anchor="middle" class="chart-label">Return %</text>`;
  return svg+"</svg>";
}

function renderSourceButtons(ex){
  const sources=availableChartSources(ex);
  if(!sources.length){$("sourceButtons").innerHTML="";return;}
  if(!sources.includes(chartSource)) chartSource=sources[0];
  $("sourceButtons").innerHTML=sources.map(s=>`<button class="chart-button ${s===chartSource?"active":""}" onclick="setChartSource('${s}')">${sourceLabel(s)}</button>`).join("");
}

function setChartSource(source){
  chartSource=source;
  renderCharts(window.__explorer||{});
}

let rollingSharpeWindow=10;

function analyticsTradeRows(){
  const set=selectedTradeDataset();
  const wanted=$('tradeSymbol')?.value||'';
  return (set?.trades||[]).filter(x=>!wanted||String(x.symbol||'')===wanted).filter(x=>x&&x.net_pnl!=null);
}

function fmtAnalytics(v, decimals=2){
  const n=Number(v);
  return Number.isFinite(n)?n.toFixed(decimals):'—';
}

function quantile(sorted,p){
  if(!sorted.length)return null;
  const idx=(sorted.length-1)*p,lo=Math.floor(idx),hi=Math.ceil(idx);
  if(lo===hi)return sorted[lo];
  return sorted[lo]+(sorted[hi]-sorted[lo])*(idx-lo);
}

function buildDrawdownSvg(rows){
  const hostRows=(rows||[]).filter(x=>x&&x.net_pnl!=null);
  if(!hostRows.length){return '<div class="trade-empty">Drawdown için trade verisi bulunamadı.</div>';}
  let cum=0,peak=0;
  const pts=hostRows.map((trade,i)=>{cum+=Number(trade.net_pnl||0);peak=Math.max(peak,cum);return {trade,index:i,cum,dd:cum-peak};});
  const minDD=Math.min(0,...pts.map(x=>x.dd));
  const maxDepth=Math.abs(minDD);
  const W=Math.max(900,pts.length*30),H=340,left=62,right=22,top=26,bottom=46;
  const pad=Math.max(maxDepth*.12,1e-9);const ymax=pad;const ymin=Math.min(-1e-9,minDD-pad);
  const Y=v=>top+(ymax-v)/(ymax-ymin)*(H-top-bottom),X=i=>left+(i+.5)*(W-left-right)/pts.length;
  let svg=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none">`;
  for(let i=0;i<=5;i++){const v=ymin+(ymax-ymin)*i/5,yy=Y(v);svg+=`<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" class="chart-gridline"/><text x="${left-8}" y="${yy+3}" text-anchor="end" class="chart-label">${v.toFixed(2)}</text>`;}
  const zero=Y(0);svg+=`<line x1="${left}" y1="${zero}" x2="${W-right}" y2="${zero}" class="chart-zero"/>`;
  let area=`M ${X(0)} ${zero}`;pts.forEach((pt,i)=>{area+=` L ${X(i)} ${Y(pt.dd)}`;});area+=` L ${X(pts.length-1)} ${zero} Z`;
  svg+=`<path d="${area}" fill="#b6314d" opacity=".13"/>`;
  let line='';pts.forEach((pt,i)=>{line+=i?` L ${X(i)} ${Y(pt.dd)}`:`M ${X(i)} ${Y(pt.dd)}`;});svg+=`<path d="${line}" fill="none" stroke="#b6314d" stroke-width="2"/>`;
  const worst=pts.reduce((a,b)=>b.dd<a.dd?b:a,pts[0]);
  pts.forEach(pt=>{const selected=Number(pt.trade.trade_id)===Number(selectedTradeId);svg+=`<circle class="pnl-point ${selected?'pnl-selected':''}" cx="${X(pt.index)}" cy="${Y(pt.dd)}" r="${selected?5:3}" fill="#b6314d" stroke="#fff" data-trade-id="${Number(pt.trade.trade_id)}" onclick="selectTrade(${Number(pt.trade.trade_id)});focusId('trades')"><title>Trade #${Number(pt.trade.trade_id)} · DD ${fmtAnalytics(pt.dd)} · cumulative ${fmtAnalytics(pt.cum)}</title></circle>`;});
  svg+=`<text x="${left}" y="16" class="pnl-note">Underwater PnL · peak-to-trough</text><text x="${W-right}" y="16" text-anchor="end" class="pnl-note">Worst ${fmtAnalytics(worst.dd)}</text><text x="${left}" y="${H-10}" class="pnl-note">trade sequence</text><text x="${W-right}" y="${H-10}" text-anchor="end" class="pnl-note">${pts.length} trades</text></svg>`;
  return svg;
}

function buildRollingSharpeSvg(rows,windowSize){
  const pts=(rows||[]).filter(x=>x&&x.net_pnl!=null).map((trade,i)=>({trade,index:i,pnl:Number(trade.net_pnl||0)}));
  if(pts.length<2 || pts.length<windowSize){return `<div class="trade-empty">Rolling Sharpe için en az ${windowSize} trade gerekiyor.</div>`;}
  const roll=[];
  for(let i=windowSize-1;i<pts.length;i++){
    const vals=pts.slice(i-windowSize+1,i+1).map(x=>x.pnl),mean=vals.reduce((a,b)=>a+b,0)/vals.length;
    const variance=vals.reduce((a,b)=>a+(b-mean)**2,0)/(vals.length-1||1),sd=Math.sqrt(variance);
    const sharpe=sd?mean/sd*Math.sqrt(windowSize):0;
    roll.push({trade:pts[i].trade,index:pts[i].index,value:sharpe});
  }
  const W=Math.max(900,roll.length*30),H=300,left=62,right=22,top=22,bottom=42;
  let min=Math.min(0,...roll.map(x=>x.value)),max=Math.max(0,...roll.map(x=>x.value));const span=Math.max(1e-9,max-min),pad=span*.12;min-=pad;max+=pad;
  const X=i=>left+(i+.5)*(W-left-right)/Math.max(1,roll.length),Y=v=>top+(max-v)/(max-min)*(H-top-bottom);
  let svg=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none">`;
  for(let i=0;i<=4;i++){const v=min+(max-min)*i/4,yy=Y(v);svg+=`<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" class="chart-gridline"/><text x="${left-8}" y="${yy+3}" text-anchor="end" class="chart-label">${v.toFixed(2)}</text>`;}
  if(min<=0&&max>=0)svg+=`<line x1="${left}" y1="${Y(0)}" x2="${W-right}" y2="${Y(0)}" class="chart-zero"/>`;
  let d='';roll.forEach((pt,i)=>{d+=i?` L ${X(i)} ${Y(pt.value)}`:`M ${X(i)} ${Y(pt.value)}`;});svg+=`<path d="${d}" fill="none" stroke="#2c69b8" stroke-width="2"/>`;
  roll.forEach(pt=>{const selected=Number(pt.trade.trade_id)===Number(selectedTradeId);const fill=pt.value>=0?'#148a5d':'#b6314d';svg+=`<circle class="pnl-point ${selected?'pnl-selected':''}" cx="${X(roll.indexOf(pt))}" cy="${Y(pt.value)}" r="${selected?4.5:2.7}" fill="${fill}" stroke="#fff" data-trade-id="${Number(pt.trade.trade_id)}" onclick="selectTrade(${Number(pt.trade.trade_id)});focusId('trades')"><title>Trade #${Number(pt.trade.trade_id)} · Rolling Sharpe ${fmtAnalytics(pt.value)}</title></circle>`;});
  svg+=`<text x="${left}" y="14" class="pnl-note">Rolling trade Sharpe · N=${windowSize}</text><text x="${W-right}" y="${H-8}" text-anchor="end" class="pnl-note">${roll.length} windows</text></svg>`;
  return svg;
}

function buildDistributionSvg(rows){
  const vals=(rows||[]).filter(x=>x&&x.net_pnl!=null).map(x=>Number(x.net_pnl)).filter(Number.isFinite);
  if(!vals.length)return '<div class="trade-empty">Dağılım için trade verisi bulunamadı.</div>';
  const sorted=[...vals].sort((a,b)=>a-b),p25=quantile(sorted,.25),median=quantile(sorted,.5),p75=quantile(sorted,.75),min=Math.min(...vals),max=Math.max(...vals);
  const W=900,H=300,left=62,right=24,top=32,bottom=54;const span=Math.max(1e-9,max-min),bins=Math.max(8,Math.min(24,Math.ceil(Math.sqrt(vals.length)*1.8))),step=span/bins,count=Array(bins).fill(0);
  vals.forEach(v=>{let idx=Math.floor((v-min)/span*bins);if(idx>=bins)idx=bins-1;if(idx<0)idx=0;count[idx]++;});
  const ymax=Math.max(...count,1),X=v=>left+(v-min)/span*(W-left-right),Y=v=>top+(ymax-v)/ymax*(H-top-bottom),bw=(W-left-right)/bins;
  let svg=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
  for(let i=0;i<=4;i++){const v=ymax*i/4,yy=Y(v);svg+=`<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" class="chart-gridline"/><text x="${left-8}" y="${yy+3}" text-anchor="end" class="chart-label">${Math.round(v)}</text>`;}
  count.forEach((c,i)=>{const a=min+i*step,b=a+step,good=(a+b)/2>=0,fill=good?'#148a5d':'#b6314d';svg+=`<rect x="${X(a)+1}" y="${Y(c)}" width="${Math.max(2,bw-2)}" height="${Math.max(1,H-bottom-Y(c))}" rx="2" fill="${fill}" opacity=".75"><title>${a.toFixed(2)} → ${b.toFixed(2)} · ${c} trades</title></rect>`;});
  [p25,median,p75].forEach((v,i)=>{if(v==null)return;const x=X(v),cls=i===1?'chart-zero':'chart-gridline';svg+=`<line x1="${x}" y1="${top}" x2="${x}" y2="${H-bottom}" class="${cls}"/><text x="${x}" y="${top-8}" text-anchor="middle" class="chart-value">${['P25','Median','P75'][i]} ${v.toFixed(2)}</text>`;});
  if(min<=0&&max>=0){const x=X(0);svg+=`<line x1="${x}" y1="${top}" x2="${x}" y2="${H-bottom}" class="chart-zero"/>`;}svg+=`<text x="${W/2}" y="${H-10}" text-anchor="middle" class="chart-label">Net PnL</text></svg>`;return svg;
}

function renderAdvancedTradeAnalytics(rows){
  const source=rows||analyticsTradeRows();
  if($('drawdownChart')){
    $('drawdownChart').innerHTML=buildDrawdownSvg(source);
    const pts=source.filter(x=>x&&x.net_pnl!=null);let cum=0,peak=0,dd=0;pts.forEach(x=>{cum+=Number(x.net_pnl||0);peak=Math.max(peak,cum);dd=Math.min(dd,cum-peak);});$('drawdownMeta').textContent=pts.length?`Max DD ${fmtAnalytics(dd)} · ${pts.length} trades`:'—';
  }
  if($('rollingSharpeChart')){$('rollingSharpeChart').innerHTML=buildRollingSharpeSvg(source,rollingSharpeWindow);$('rollingSharpeMeta').textContent=`window ${rollingSharpeWindow}`;}
  if($('distributionChart')){const vals=source.map(x=>Number(x.net_pnl)).filter(Number.isFinite),med=quantile([...vals].sort((a,b)=>a-b),.5),wins=vals.filter(v=>v>0).length;$('distributionChart').innerHTML=buildDistributionSvg(source);$('distributionMeta').textContent=vals.length?`Median ${fmtAnalytics(med)} · Win ${fmtAnalytics(wins/vals.length*100)}%`:'—';}
}


let stressBps=0;
function fmtMoney(v){return Number.isFinite(Number(v))?Number(v).toFixed(2):"—";}
function pctNum(v){return Number.isFinite(Number(v))?Number(v).toFixed(2)+"%":"—";}
function medianValue(vals){const a=vals.filter(Number.isFinite).sort((x,y)=>x-y);if(!a.length)return null;const m=Math.floor(a.length/2);return a.length%2?a[m]:(a[m-1]+a[m])/2;}
function buildRegimeRows(rows){
  const clean=(rows||[]).filter(r=>r&&r.close!=null).map(r=>({...r,close:Number(r.close),high:Number(r.high),low:Number(r.low)}));
  const out=[]; const vols=[];
  for(let i=0;i<clean.length;i++){
    const r=clean[i], c=r.close;
    const prev=clean[Math.max(0,i-1)]?.close;
    const ret=prev?Math.log(c/prev):0;
    const w=clean.slice(Math.max(0,i-19),i+1).map((x,j,arr)=>{const prevC=j?arr[j-1].close:null;return prevC?Math.log(x.close/prevC):null;}).filter(Number.isFinite);
    const vol=w.length>=5?Math.sqrt(w.reduce((a,x)=>a+x*x,0)/w.length)*Math.sqrt(252):null;
    vols.push(vol);
    let ema20=c,ema50=c;
    const alpha20=2/21,alpha50=2/51;
    if(i>0){ema20=clean[i-1].__ema20??c;ema50=clean[i-1].__ema50??c;}
    ema20=i===0?c:alpha20*c+(1-alpha20)*ema20;ema50=i===0?c:alpha50*c+(1-alpha50)*ema50;
    r.__ema20=ema20;r.__ema50=ema50;
    const spread=Math.abs(ema20-ema50)/(Math.abs(c)||1);
    const trend=spread<0.003?"SIDEWAYS":ema20>ema50?"TREND UP":"TREND DOWN";
    out.push({...r,ret,vol,trend});
  }
  const validVol=vols.filter(Number.isFinite),volMed=medianValue(validVol);
  out.forEach(r=>r.volRegime=Number.isFinite(r.vol)&&Number.isFinite(volMed)&&r.vol>volMed*1.35?"HIGH VOL":"NORMAL VOL");
  return out;
}
function regimeAtDate(date,rows){
  if(!date||!rows.length)return null; const target=new Date(String(date).slice(0,10));let best=rows[0],dist=Infinity;
  rows.forEach(r=>{const d=Math.abs(new Date(String(r.timestamp).slice(0,10))-target);if(d<dist){dist=d;best=r;}});return best;
}
function buildRegimeTimelineHtml(rows){
  if(!rows.length)return '<div class="trade-empty">Regime verisi bulunamadı.</div>';
  const step=Math.max(1,Math.floor(rows.length/140)), sampled=[];
  for(let i=0;i<rows.length;i+=step)sampled.push(rows[i]);
  return sampled.map(r=>{const cls=r.trend==="TREND UP"?"regime-trend-up":r.trend==="TREND DOWN"?"regime-trend-down":"regime-sideways";const vol=r.volRegime==="HIGH VOL"?" regime-high-vol":"";const label=r.trend.replace("TREND ","");return `<div class="regime-seg ${cls}${vol}" title="${String(r.timestamp).slice(0,10)} · ${r.trend} · ${r.volRegime}${Number.isFinite(r.vol)?" · vol "+(r.vol*100).toFixed(1)+"%":""}"><span>${label}</span></div>`;}).join('');
}
function renderRegimeAndStress(){
  const timeline=$('regimeTimeline'),perf=$('regimePerformance'),stress=$('stressPanel'),dd=$('ddDurationChart');
  if(!timeline||!perf||!stress||!dd)return;
  const rows=(tvResearchRows||[]).filter(r=>r&&r.close!=null);
  const regimeRows=buildRegimeRows(rows);
  timeline.innerHTML=buildRegimeTimelineHtml(regimeRows);
  $('regimeTimelineMeta').textContent=regimeRows.length?`${regimeRows[0].timestamp?.slice(0,10)||'—'} → ${regimeRows[regimeRows.length-1].timestamp?.slice(0,10)||'—'}`:'—';
  const trades=analyticsTradeRows().filter(x=>x&&x.net_pnl!=null);
  const groups={"TREND UP":[],"TREND DOWN":[],"SIDEWAYS":[]};
  trades.forEach(t=>{const r=regimeAtDate(t.entry_time||t.exit_time,regimeRows);if(r)groups[r.trend].push(t);});
  perf.innerHTML=Object.entries(groups).map(([name,arr])=>{const pnl=arr.reduce((a,x)=>a+Number(x.net_pnl||0),0),wins=arr.filter(x=>Number(x.net_pnl||0)>0).length,ret=arr.length?arr.reduce((a,x)=>a+Number(x.return_percent||0),0)/arr.length:null;const chip=name==='TREND UP'?'regime-up':name==='TREND DOWN'?'regime-down':'regime-flat';return `<div class="regime-row"><div><span class="regime-chip ${chip}">${name}</span></div><div><b>${arr.length}</b> trades</div><div>PnL <b>${fmtMoney(pnl)}</b></div><div>Win <b>${arr.length?((wins/arr.length)*100).toFixed(1):'—'}%</b></div><div>Avg <b>${ret==null?'—':ret.toFixed(2)+'%'}</b></div></div>`;}).join('');
  $('regimePerfMeta').textContent=`${trades.length} trades mapped`;
  const bps=stressBps, costRate=bps/10000, stressed=trades.map(t=>({...t,stressPnl:Number(t.net_pnl||0)-Math.abs(Number(t.entry_price)||0)*costRate-Math.abs(Number(t.exit_price)||0)*costRate}));
  const base=trades.reduce((a,x)=>a+Number(x.net_pnl||0),0),net=stressed.reduce((a,x)=>a+Number(x.stressPnl||0),0),wins=stressed.filter(x=>x.stressPnl>0).length;
  const pf=(vals=>{const pos=vals.filter(v=>v>0).reduce((a,v)=>a+v,0),neg=-vals.filter(v=>v<0).reduce((a,v)=>a+v,0);return neg?pos/neg:null;})(stressed.map(x=>x.stressPnl));
  stress.innerHTML=`<div class="stress-kpi"><div class="metric"><div class="cap">Stressed Net PnL</div><div class="n">${fmtMoney(net)}</div></div><div class="metric"><div class="cap">Δ vs Base</div><div class="n">${fmtMoney(net-base)}</div></div><div class="metric"><div class="cap">Win Rate</div><div class="n">${trades.length?(wins/trades.length*100).toFixed(1):'—'}%</div></div></div><div class="stress-row"><span>Base</span><span>${fmtMoney(base)}</span><span>PF ${pf==null?'—':pf.toFixed(2)}</span></div><div class="stress-row"><span>${bps} bps</span><span>${fmtMoney(net)}</span><span>PF ${pf==null?'—':pf.toFixed(2)}</span></div>`;
  $('stressMeta').textContent=`${bps} bps`;
  let cum=0,peak=0,duration=0,maxDuration=0,series=[];trades.forEach((t,i)=>{cum+=Number(t.net_pnl||0);if(cum>=peak){peak=cum;duration=0;}else{duration+=1;maxDuration=Math.max(maxDuration,duration);}series.push({i,t,duration});});
  const W=900,H=250,left=62,right=24,top=24,bottom=42,maxD=Math.max(1,maxDuration),Y=v=>top+(maxD-v)/maxD*(H-top-bottom),X=i=>left+(i+.5)*(W-left-right)/Math.max(series.length,1);
  let svg=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;for(let i=0;i<=5;i++){const v=maxD*i/5,yy=Y(v);svg+=`<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" class="chart-gridline"/><text x="${left-8}" y="${yy+3}" text-anchor="end" class="chart-label">${Math.round(v)}</text>`;}
  if(series.length){let d='';series.forEach((p,i)=>d+=i?` L ${X(i)} ${Y(p.duration)}`:`M ${X(i)} ${Y(p.duration)}`);svg+=`<path d="${d}" fill="none" stroke="#b6314d" stroke-width="2.2"/>`;series.forEach((p,i)=>{if(p.duration>0)svg+=`<circle cx="${X(i)}" cy="${Y(p.duration)}" r="2.8" fill="#b6314d"><title>Trade #${p.t.trade_id} · DD duration ${p.duration} trades</title></circle>`;});}
  svg+=`<text x="${left}" y="16" class="pnl-note">Consecutive trades below prior equity peak</text><text x="${W-right}" y="${H-10}" text-anchor="end" class="pnl-note">Max duration ${maxDuration} trades</text></svg>`;dd.innerHTML=svg;$('ddDurationMeta').textContent=series.length?`Max ${maxDuration} trades · ${series.length} trades`:'—';
  $('regimeMeta').textContent=`${regimeRows.length?regimeRows.length:0} bars · heuristic regimes · stress ${bps} bps`;
}
function setStressBps(bps,button){stressBps=Number(bps)||0;document.querySelectorAll('[data-stress-bps]').forEach(el=>el.classList.toggle('active',Number(el.dataset.stressBps)===stressBps));renderRegimeAndStress();}

function setRollingSharpeWindow(size,button){rollingSharpeWindow=Number(size)||10;document.querySelectorAll('[data-rs-window]').forEach(el=>el.classList.toggle('active',Number(el.dataset.rsWindow)===rollingSharpeWindow));renderAdvancedTradeAnalytics(analyticsTradeRows());}

function buildMonteCarloSvg(values,simulations=250){
  const clean=(values||[]).map(Number).filter(Number.isFinite);
  if(clean.length<3)return '<div class="trade-empty">Monte Carlo için en az 3 trade gerekiyor.</div>';
  const n=Math.min(clean.length,300),src=clean.slice(-n),steps=n,sims=Math.max(50,Math.min(Number(simulations)||250,500));
  const paths=[],bands=[];
  for(let s=0;s<sims;s++){let cum=0,path=[];for(let i=0;i<steps;i++){const v=src[Math.floor(Math.random()*src.length)];cum+=v;path.push(cum);}paths.push(path);}
  for(let i=0;i<steps;i++){const vals=paths.map(p=>p[i]).sort((a,b)=>a-b);bands.push({p5:quantile(vals,.05),p50:quantile(vals,.5),p95:quantile(vals,.95)});}
  const finals=paths.map(p=>p[p.length-1]).sort((a,b)=>a-b);
  const W=900,H=300,left=58,right=20,top=24,bottom=40,minV=Math.min(...bands.map(x=>x.p5)),maxV=Math.max(...bands.map(x=>x.p95)),span=(maxV-minV)||1,pad=span*.08;
  const ymin=minV-pad,ymax=maxV+pad,X=i=>left+(i/(steps-1||1))*(W-left-right),Y=v=>top+(ymax-v)/(ymax-ymin)*(H-top-bottom);
  let svg=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
  for(let i=0;i<=5;i++){const v=ymin+(ymax-ymin)*i/5,yy=Y(v);svg+=`<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" class="chart-gridline"/><text x="${left-7}" y="${yy+3}" text-anchor="end" class="chart-label">${fmtAnalytics(v)}</text>`;}
  let upper='',lower='',median='';bands.forEach((b,i)=>{upper+=i?` L ${X(i)} ${Y(b.p95)}`:`M ${X(i)} ${Y(b.p95)}`;lower=i?` L ${X(i)} ${Y(b.p5)}`:`M ${X(i)} ${Y(b.p5)}`;median+=i?` L ${X(i)} ${Y(b.p50)}`:`M ${X(i)} ${Y(b.p50)}`;});
  const rev=bands.map((b,i)=>({i,b})).reverse();let area=upper;rev.forEach(({i,b})=>area+=` L ${X(i)} ${Y(b.p5)}`);area+=' Z';
  svg+=`<path d="${area}" fill="#dbeeff" opacity=".8"/><path d="${upper}" fill="none" stroke="#89aeda" stroke-width="1"/><path d="${lower}" fill="none" stroke="#89aeda" stroke-width="1"/><path d="${median}" fill="none" stroke="#111" stroke-width="2.2"/>`;
  if(ymin<=0&&ymax>=0)svg+=`<line x1="${left}" y1="${Y(0)}" x2="${W-right}" y2="${Y(0)}" class="chart-zero"/>`;
  svg+=`<text x="${left}" y="16" class="pnl-note">5–95% envelope · median path</text><text x="${W-right}" y="16" text-anchor="end" class="pnl-note">${sims} simulations · ${steps} sampled trades</text><text x="${W/2}" y="${H-8}" text-anchor="middle" class="chart-label">Resampled trade sequence</text></svg>`;
  return svg;
}

function computeMaeMfe(trades){
  const bars=Array.isArray(tvResearchRows)?tvResearchRows.filter(r=>r&&r.close!=null):[];
  if(!bars.length)return [];
  const out=[];
  (trades||[]).forEach(t=>{
    const entry=Number(t.entry_price);if(!Number.isFinite(entry)||entry===0)return;
    const side=String(t.side||'LONG').toUpperCase();
    const ei=findClosestIndex(bars,t.entry_time),xi=findClosestIndex(bars,t.exit_time);
    if(ei==null||xi==null)return;
    const lo=Math.min(ei,xi),hi=Math.max(ei,xi),slice=bars.slice(lo,hi+1);
    const highs=slice.map(x=>Number(x.high)).filter(Number.isFinite),lows=slice.map(x=>Number(x.low)).filter(Number.isFinite);
    if(!highs.length||!lows.length)return;
    let mae,mfe;
    if(side.includes('SHORT')){mfe=(entry-Math.min(...lows))/entry*100;mae=-(Math.max(...highs)-entry)/entry*100;}
    else {mfe=(Math.max(...highs)-entry)/entry*100;mae=-(entry-Math.min(...lows))/entry*100;}
    out.push({trade:t,mae,mfe});
  });
  return out;
}

function buildMaeMfeSvg(rows){
  if(!rows.length)return '<div class="trade-empty">MAE/MFE için trade ile eşleşen OHLCV bulunamadı.</div>';
  const xs=rows.map(x=>x.mae),ys=rows.map(x=>x.mfe),xmin=Math.min(-1,...xs),xmax=Math.max(1,...xs),ymin=0,ymax=Math.max(1,...ys)*1.1;
  const W=900,H=290,left=62,right=25,top=20,bottom=42,xspan=xmax-xmin||1;const X=v=>left+(v-xmin)/xspan*(W-left-right);const Y=v=>top+(ymax-v)/(ymax-ymin)*(H-top-bottom);
  let svg=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
  for(let i=0;i<=5;i++){const xv=xmin+xspan*i/5,xx=X(xv),yv=ymin+(ymax-ymin)*i/5,yy=Y(yv);svg+=`<line x1="${xx}" y1="${top}" x2="${xx}" y2="${H-bottom}" class="chart-gridline"/><text x="${xx}" y="${H-18}" text-anchor="middle" class="chart-label">${xv.toFixed(1)}%</text><line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" class="chart-gridline"/><text x="${left-7}" y="${yy+3}" text-anchor="end" class="chart-label">${yv.toFixed(1)}%</text>`;}
  if(xmin<=0&&xmax>=0)svg+=`<line x1="${X(0)}" y1="${top}" x2="${X(0)}" y2="${H-bottom}" class="chart-zero"/>`;
  rows.forEach(r=>{const pnl=Number(r.trade.net_pnl||0),fill=pnl>=0?'#148a5d':'#b6314d',sel=Number(r.trade.trade_id)===Number(selectedTradeId);svg+=`<circle cx="${X(r.mae)}" cy="${Y(r.mfe)}" r="${sel?5.5:4}" fill="${fill}" opacity=".85" stroke="#fff" stroke-width="${sel?2:1}" onclick="selectTrade(${Number(r.trade.trade_id)});focusId('trades')"><title>Trade #${Number(r.trade.trade_id)} · MAE ${fmtAnalytics(r.mae)}% · MFE ${fmtAnalytics(r.mfe)}% · PnL ${fmtAnalytics(pnl)}</title></circle>`;});
  svg+=`<text x="${W/2}" y="${H-4}" text-anchor="middle" class="chart-label">MAE %</text><text x="14" y="${H/2}" transform="rotate(-90 14 ${H/2})" text-anchor="middle" class="chart-label">MFE %</text></svg>`;return svg;
}

function renderStreakDiagnostics(trades){
  const vals=(trades||[]).map(t=>Number(t.net_pnl)).filter(Number.isFinite);if(!vals.length){$('streakBars').innerHTML='<div class="trade-empty">Streak verisi yok.</div>';return;}
  const streaks=[],maxByType={WIN:0,LOSS:0},all=[];let type=null,len=0;
  vals.forEach(v=>{const next=v>0?'WIN':v<0?'LOSS':'FLAT';if(next===type&&next!=='FLAT'){len++;}else{if(type&&type!=='FLAT')streaks.push({type,len});type=next;len=next==='FLAT'?0:1;}if(type!=='FLAT'&&len>maxByType[type])maxByType[type]=len;if(next!=='FLAT')all.push(next);});if(type&&type!=='FLAT')streaks.push({type,len});
  const currentType=all[all.length-1]||'FLAT';let currentLen=0;for(let i=vals.length-1;i>=0;i--){const v=vals[i],t=v>0?'WIN':v<0?'LOSS':'FLAT';if(t!==currentType)break;currentLen++;}const avg=streaks.length?streaks.reduce((a,x)=>a+x.len,0)/streaks.length:null;
  $('longWin').textContent=String(maxByType.WIN||0);$('longLoss').textContent=String(maxByType.LOSS||0);$('currentStreak').textContent=`${currentType} ${currentLen}`;$('avgStreak').textContent=avg==null?'—':avg.toFixed(2);$('streakMeta').textContent=`${streaks.length} streaks`;
  const recent=streaks.slice(-10).reverse(),mx=Math.max(1,...recent.map(x=>x.len));$('streakBars').innerHTML=recent.length?recent.map((x,i)=>`<div class="streak-row"><span>${x.type} #${recent.length-i}</span><div class="streak-track"><div class="streak-fill" style="width:${(x.len/mx*100).toFixed(1)}%;background:${x.type==='WIN'?'#148a5d':'#b6314d'}"></div></div><b>${x.len}</b></div>`).join(''):'<div class="trade-empty">Streak bulunamadı.</div>';
}

function renderTradeDiagnostics(){
  const trades=analyticsTradeRows().filter(x=>x&&x.net_pnl!=null);
  const pnl=trades.map(x=>Number(x.net_pnl)).filter(Number.isFinite);
  const mc= $('monteCarloChart');
  if(mc){mc.innerHTML=buildMonteCarloSvg(pnl,250);if(pnl.length>=3){const finals=[];for(let s=0;s<250;s++){let c=0;for(let i=0;i<pnl.length;i++)c+=pnl[Math.floor(Math.random()*pnl.length)];finals.push(c);}finals.sort((a,b)=>a-b);$('mcP5').textContent=fmtAnalytics(quantile(finals,.05));$('mcP50').textContent=fmtAnalytics(quantile(finals,.5));$('mcP95').textContent=fmtAnalytics(quantile(finals,.95));$('mcProb').textContent=fmtAnalytics(finals.filter(v=>v>0).length/finals.length*100)+'%';$('mcMeta').textContent=`250 paths · ${pnl.length} trades`;}else{$('mcP5').textContent='—';$('mcP50').textContent='—';$('mcP95').textContent='—';$('mcProb').textContent='—';}}
  const maeRows=computeMaeMfe(trades),mae=maeRows.map(x=>x.mae),mfe=maeRows.map(x=>x.mfe);$('maeMfeChart').innerHTML=buildMaeMfeSvg(maeRows);$('maeMfeMeta').textContent=`${maeRows.length} mapped trades`;$('maeMedian').textContent=mae.length?fmtAnalytics(quantile([...mae].sort((a,b)=>a-b),.5))+'%':'—';$('mfeMedian').textContent=mfe.length?fmtAnalytics(quantile([...mfe].sort((a,b)=>a-b),.5))+'%':'—';$('mfeBest').textContent=mfe.length?fmtAnalytics(Math.max(...mfe))+'%':'—';$('maeWorst').textContent=mae.length?fmtAnalytics(Math.min(...mae))+'%':'—';
  renderStreakDiagnostics(trades);$('diagnosticsMeta').textContent=`${trades.length} trades · selected dataset`;
}


function renderCharts(ex){
  window.__explorer=ex;
  renderSourceButtons(ex);
  const records=getChartRecords(ex);
  $("chartMeta").textContent=`${sourceLabel(chartSource)} · ${records.length} symbol`;
  $("returnChart").innerHTML=buildBarSvg(records,"return_percent","%");
  $("pfChart").innerHTML=buildPfSvg(records);
  $("scatterChart").innerHTML=buildScatterSvg(records);
  renderAdvancedTradeAnalytics(analyticsTradeRows());
}

function renderTradePnlCurve(rows){
  const host=$("tradePnlChart");
  if(!host)return;
  const pts=(rows||[]).filter(x=>x&&x.net_pnl!=null);
  if(!pts.length){host.innerHTML='<div class="trade-empty">Trade PnL verisi bulunamadı.</div>';return;}
  let cumulative=0,maxCum=0;
  const series=pts.map((trade,index)=>{
    cumulative+=Number(trade.net_pnl||0);
    maxCum=Math.max(maxCum,cumulative);
    return {trade,index,cum:cumulative,dd:cumulative-maxCum};
  });
  const W=Math.max(900,series.length*34),H=340,left=62,right=22,top=26,bottom=46;
  const vals=[0,...series.map(x=>x.cum)];
  let min=Math.min(...vals),max=Math.max(...vals);
  const span=(max-min)||1,pad=span*.12;
  min-=pad;max+=pad;
  const X=i=>left+(i+.5)*(W-left-right)/series.length;
  const Y=v=>top+(max-v)/(max-min)*(H-top-bottom);
  let svg=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none" class="pnl-chart-wrap">`;
  for(let i=0;i<=5;i++){
    const v=min+(max-min)*i/5,yy=Y(v);
    svg+=`<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" class="chart-gridline"/>`;
    svg+=`<text x="${left-8}" y="${yy+3}" text-anchor="end" class="chart-label">${v.toFixed(2)}</text>`;
  }
  const zero=Y(0);
  if(zero>=top&&zero<=H-bottom)svg+=`<line x1="${left}" y1="${zero}" x2="${W-right}" y2="${zero}" class="chart-zero"/>`;
  let d="";
  series.forEach((pt,i)=>{d+=i?` L ${X(i)} ${Y(pt.cum)}`:`M ${X(i)} ${Y(pt.cum)}`;});
  svg+=`<path d="${d}" fill="none" stroke="#2c69b8" stroke-width="2.5"/>`;
  series.forEach((pt,i)=>{
    const pnl=Number(pt.trade.net_pnl||0);
    const fill=pnl>0?"#148a5d":pnl<0?"#b6314d":"#9a6a07";
    const selected=Number(pt.trade.trade_id)===Number(selectedTradeId);
    const date=String(pt.trade.exit_time||pt.trade.entry_time||"").slice(0,10);
    svg+=`<circle class="pnl-point ${selected?'pnl-selected':''}" cx="${X(i)}" cy="${Y(pt.cum)}" r="${selected?5:3.5}" fill="${fill}" stroke="#fff" data-trade-id="${Number(pt.trade.trade_id)}" onclick="selectTrade(${Number(pt.trade.trade_id)});focusId('trades')"><title>Trade #${Number(pt.trade.trade_id)} · ${date} · PnL ${pnl.toFixed(2)} · cumulative ${pt.cum.toFixed(2)}</title></circle>`;
  });
  svg+=`<text x="${left}" y="16" class="pnl-note">Cumulative Net PnL · selected dataset</text>`;
  svg+=`<text x="${W-right}" y="${H-10}" text-anchor="end" class="pnl-note">${series.length} trades</text>`;
  svg+='</svg>';
  host.innerHTML=svg;
}



function tradeOutcome(trade){
  const pnl=Number(trade.net_pnl||0);
  return pnl>0 ? "WIN" : pnl<0 ? "LOSS" : "FLAT";
}

function tradeFilteredRows(rows){
  const outcome=$("tradeOutcome")?.value||"ALL";
  const side=$("tradeSide")?.value||"ALL";
  return rows.filter(r=>{
    const okOutcome=outcome==="ALL" || tradeOutcome(r)===outcome;
    const okSide=side==="ALL" || String(r.side||"").toUpperCase()===side;
    return okOutcome && okSide;
  });
}

function buildTradePriceMap(trade){
  if(!trade){
    $("tradePriceMap").innerHTML='<div class="muted" style="padding:20px">Bir trade seçin.</div>';
    return;
  }

  const points=[];
  const add=(name,value)=>{
    if(value!=null && Number.isFinite(Number(value))) points.push({name,value:Number(value)});
  };
  add("Entry",trade.entry_price);
  add("Exit",trade.exit_price);
  add("SL",trade.stop_price);
  add("TP",trade.target_price);

  if(points.length<2){
    $("tradePriceMap").innerHTML='<div class="muted" style="padding:20px">Grafik için yeterli fiyat alanı yok.</div>';
    return;
  }

  const vals=points.map(p=>p.value);
  const min=Math.min(...vals), max=Math.max(...vals), pad=((max-min)||1)*0.20;
  const lo=min-pad, hi=max+pad, W=1000, H=230, left=88, right=28, top=20, bottom=32;
  const Y=v=>top+(hi-v)/(hi-lo)*(H-top-bottom);
  const entry=Number(trade.entry_price), exit=Number(trade.exit_price);
  const entryY=Y(entry), exitY=Y(exit);

  let svg=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;
  for(let i=0;i<=5;i++){
    const v=lo+(hi-lo)*i/5, yy=Y(v);
    svg+=`<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" class="chart-gridline"/>`;
    svg+=`<text x="${left-10}" y="${yy+3}" text-anchor="end" class="chart-label">${v.toFixed(4)}</text>`;
  }

  const x1=250,x2=750;
  svg+=`<line x1="${x1}" y1="${entryY}" x2="${x2}" y2="${exitY}" stroke="#111" stroke-width="2"/>`;
  svg+=`<circle cx="${x1}" cy="${entryY}" r="7" fill="#2c69b8"/><circle cx="${x2}" cy="${exitY}" r="7" fill="#111"/>`;
  svg+=`<text x="${x1}" y="${entryY-12}" text-anchor="middle" class="chart-value">ENTRY ${entry.toFixed(4)}</text>`;
  svg+=`<text x="${x2}" y="${exitY-12}" text-anchor="middle" class="chart-value">EXIT ${exit.toFixed(4)}</text>`;
  svg+=`<text x="18" y="18" class="chart-label">${esc(trade.symbol||"")}</text>`;

  if(trade.stop_price!=null){
    const sy=Y(Number(trade.stop_price));
    svg+=`<line x1="${left}" y1="${sy}" x2="${W-right}" y2="${sy}" stroke="#b6314d" stroke-width="1.5" stroke-dasharray="6 4"/>`;
    svg+=`<text x="${W-right}" y="${sy-5}" text-anchor="end" class="chart-value">SL ${Number(trade.stop_price).toFixed(4)}</text>`;
  }
  if(trade.target_price!=null){
    const ty=Y(Number(trade.target_price));
    svg+=`<line x1="${left}" y1="${ty}" x2="${W-right}" y2="${ty}" stroke="#148a5d" stroke-width="1.5" stroke-dasharray="6 4"/>`;
    svg+=`<text x="${W-right}" y="${ty-5}" text-anchor="end" class="chart-value">TP ${Number(trade.target_price).toFixed(4)}</text>`;
  }

  svg+=`<text x="${x1}" y="${H-8}" text-anchor="middle" class="chart-label">${esc(short(trade.entry_time,34))}</text>`;
  svg+=`<text x="${x2}" y="${H-8}" text-anchor="middle" class="chart-label">${esc(short(trade.exit_time,34))}</text>`;
  svg+="</svg>";

  $("tradePriceMap").innerHTML=svg;
}

function updateTradeMetricCards(rows){
  const wins=rows.filter(r=>Number(r.net_pnl||0)>0).length;
  const losses=rows.filter(r=>Number(r.net_pnl||0)<0).length;
  const net=rows.reduce((a,r)=>a+Number(r.net_pnl||0),0);
  const avgReturn=rows.length?rows.reduce((a,r)=>a+Number(r.return_percent||0),0)/rows.length:null;
  $("tradeCount").textContent=num(rows.length);
  $("tradeWins").textContent=num(wins);
  $("tradeLosses").textContent=num(losses);
  $("tradeWinRate").textContent=rows.length?(wins/rows.length*100).toFixed(2)+"%":"—";
  $("tradeNetPnl").textContent=net.toFixed(2);
  $("tradeAvgReturn").textContent=avgReturn==null?"—":avgReturn.toFixed(2)+"%";
}

let tradeData = null;
let selectedTradeId = null;

async function loadTrades(){
  try{
    const response = await get("/api/trades");
    tradeData = response.data || {};
    renderTradeControls();
    renderSelectedTrades();
  }catch(e){
    $("tradeMeta").textContent="Trade data unavailable";
    $("tradeTable").innerHTML=`<tr><td colspan="12">Trade Viewer verisi alınamadı: ${esc(e.message)}</td></tr>`;
  }
}

function renderTradeControls(){
  const dataset=$("tradeDataset"), symbol=$("tradeSymbol");
  const sets=tradeData?.datasets||[];

  dataset.innerHTML=sets.length
    ? sets.map((x,i)=>`<option value="${i}">${esc(x.symbol||"DATASET")} · ${x.trades?.length||0} trades</option>`).join("")
    : '<option value="">No trade artifact</option>';

  if(!sets.length){
    symbol.innerHTML='<option value="">—</option>';
    return;
  }

  renderTradeSymbols();
}

function renderTradeSymbols(){
  const previous=$("tradeSymbol")?.value||"";
  const idx=Number($("tradeDataset").value||0);
  const set=tradeData?.datasets?.[idx];
  const symbols=[...new Set((set?.trades||[]).map(x=>x.symbol).filter(Boolean))];
  $("tradeSymbol").innerHTML=symbols.length
    ? symbols.map(s=>`<option value="${esc(s)}">${esc(s)}</option>`).join("")
    : '<option value="">—</option>';
  if(previous && symbols.includes(previous)) $("tradeSymbol").value=previous;
}

function selectedTradeDataset(){
  const idx=Number($("tradeDataset").value||0);
  return tradeData?.datasets?.[idx]||null;
}

function renderSelectedTrades(){
  if(!tradeData)return;

  const set=selectedTradeDataset();
  const wanted=$("tradeSymbol")?.value||"";
  let rows=(set?.trades||[]).filter(x=>!wanted||String(x.symbol||"")===wanted);
  rows=tradeFilteredRows(rows);
  renderTradePnlCurve(rows);
  renderAdvancedTradeAnalytics(rows);
  renderTradeDiagnostics();

  $("tradeMeta").textContent=`${rows.length} trade · ${set?.source||"—"}`;
  updateTradeMetricCards(rows);

  $("tradeTable").innerHTML=rows.length?rows.map(x=>{
    const id=Number(x.trade_id);
    const pnl=Number(x.net_pnl||0);
    const outcome=tradeOutcome(x);
    return `<tr class="trade-row ${id===selectedTradeId?'selected':''}" onclick="selectTrade(${id})">
      <td>${id}</td>
      <td><span class="tag ${x.side==="LONG"?"safe":"info"}">${esc(x.side||"—")}</span></td>
      <td>${esc(short(x.entry_time,28))}</td>
      <td>${esc(short(x.exit_time,28))}</td>
      <td>${x.entry_price==null?"—":Number(x.entry_price).toFixed(4)}</td>
      <td>${x.exit_price==null?"—":Number(x.exit_price).toFixed(4)}</td>
      <td>${x.stop_price==null?"—":Number(x.stop_price).toFixed(4)}</td>
      <td>${x.target_price==null?"—":Number(x.target_price).toFixed(4)}</td>
      <td>${pnl.toFixed(2)}</td>
      <td>${x.return_percent==null?"—":Number(x.return_percent).toFixed(2)+"%"}</td>
      <td>${x.bars_held==null?"—":num(x.bars_held)}</td>
      <td>${esc(x.exit_reason||outcome||"—")}</td>
    </tr>`;
  }).join(""): '<tr><td colspan="12">Bu filtreye ait trade kaydı bulunamadı.</td></tr>';

  if(selectedTradeId!=null){
    const selected=rows.find(x=>Number(x.trade_id)===selectedTradeId);
    if(selected) renderTradeDetail(selected);
    else {
      selectedTradeId=null;
      clearTradeDetail();
    }
  }else if(rows.length){
    selectTrade(Number(rows[0].trade_id));
  }
}

function selectTrade(id){
  selectedTradeId=Number(id);
  renderSelectedTrades();
  renderTradeChartForSelected();
}

let tradeViewMode="FIT";

function setTradeViewMode(mode){
  tradeViewMode=mode==="FULL"?"FULL":"FIT";
  $("tradeViewFit")?.classList.toggle("active",tradeViewMode==="FIT");
  $("tradeViewFull")?.classList.toggle("active",tradeViewMode==="FULL");
  renderTradeChartForSelected();
}

function tradeStatusClass(trade){
  const pnl=Number(trade?.net_pnl||0);
  return pnl>0?"safe":pnl<0?"bad":"warn";
}

function renderTradeSummary(trade){
  if(!trade){
    $("tradeSummary").innerHTML="";
    $("tradeLevels").innerHTML="";
    return;
  }
  const outcome=tradeOutcome(trade);
  const cls=tradeStatusClass(trade);
  $("tradeSummary").innerHTML=`
    <div class="metric"><div class="cap">Outcome</div><div class="n"><span class="tag ${cls}">${esc(outcome)}</span></div></div>
    <div class="metric"><div class="cap">Entry</div><div class="n">${trade.entry_price==null?"—":Number(trade.entry_price).toFixed(4)}</div></div>
    <div class="metric"><div class="cap">Exit</div><div class="n">${trade.exit_price==null?"—":Number(trade.exit_price).toFixed(4)}</div></div>
    <div class="metric"><div class="cap">Net PnL</div><div class="n">${trade.net_pnl==null?"—":Number(trade.net_pnl).toFixed(2)}</div></div>
    <div class="metric"><div class="cap">Return</div><div class="n">${trade.return_percent==null?"—":Number(trade.return_percent).toFixed(2)+"%"}</div></div>
    <div class="metric"><div class="cap">Bars Held</div><div class="n">${trade.bars_held==null?"—":num(trade.bars_held)}</div></div>`;

  const level=(label,value,cls)=>value==null?"":`<span class="trade-level ${cls}">${label} ${Number(value).toFixed(4)}</span>`;
  $("tradeLevels").innerHTML=
    level("ENTRY",trade.entry_price,"entry")+
    level("EXIT",trade.exit_price,"exit")+
    level("SL",trade.stop_price,"sl")+
    level("TP",trade.target_price,"tp");
}

function findClosestIndex(points,dt){
  if(!dt||!points.length)return null;
  const target=new Date(String(dt).replace(" ","T"));
  let best=0,dist=Infinity;
  points.forEach((r,i)=>{
    const d=Math.abs(new Date(r.timestamp)-target);
    if(d<dist){dist=d;best=i;}
  });
  return best;
}

function cropTradeRows(rows,trade){
  if(tradeViewMode==="FULL"||!rows.length)return rows;
  const ei=findClosestIndex(rows,trade.entry_time);
  const xi=findClosestIndex(rows,trade.exit_time);
  if(ei==null&&xi==null)return rows;
  const centerStart=Math.min(ei==null?xi:ei,xi==null?ei:xi);
  const centerEnd=Math.max(ei==null?xi:ei,xi==null?ei:xi);
  const pad=6;
  const a=Math.max(0,centerStart-pad);
  const b=Math.min(rows.length,centerEnd+pad+1);
  return rows.slice(a,b);
}

async function renderTradeChartForSelected(){
  const set=selectedTradeDataset();
  const wanted=$("tradeSymbol")?.value||"";
  const rows=(set?.trades||[]).filter(x=>!wanted||String(x.symbol||"")===wanted);
  const selected=rows.find(x=>Number(x.trade_id)===selectedTradeId);
  if(!selected){
    $("tradeChartStatus").textContent="Bir trade seçin.";
    $("tradePriceMap").innerHTML='<div class="trade-empty">Bir trade seçin.</div>';
    renderTradeSummary(null);
    return;
  }

  renderTradeSummary(selected);
  $("tradeChartStatus").textContent="Gerçek OHLCV yükleniyor…";
  try{
    const params=new URLSearchParams();
    params.set("symbol",selected.symbol||"");
    params.set("entry_time",selected.entry_time||"");
    params.set("exit_time",selected.exit_time||"");
    const response=await get("/api/trade-chart?"+params.toString());
    const data=response.data||{};
    if(!data.available||!data.rows?.length) throw new Error(data.error||"OHLCV bulunamadı.");
    $("tradeChartStatus").textContent=`${data.symbol} · ${data.bars} günlük bar · ${data.start} → ${data.end} · ${tradeViewMode==="FIT"?"trade zoom":"full window"}`;
    drawRealTradeChart(data.rows,selected);
  }catch(e){
    $("tradeChartStatus").textContent="Chart unavailable";
    $("tradePriceMap").innerHTML=`<div class="trade-empty">Gerçek OHLCV alınamadı: ${esc(e.message)}</div>`;
  }
}

function drawRealTradeChart(rows,trade){
  const showEma=($("tradeIndicator")?.value||"EMA")==="EMA";
  const allPts=rows.filter(r=>r.open!=null&&r.high!=null&&r.low!=null&&r.close!=null);
  const pts=cropTradeRows(allPts,trade);
  if(!pts.length){$("tradePriceMap").innerHTML='<div class="trade-empty">Candle verisi yok.</div>';return;}

  const W=Math.max(1200,pts.length*34),H=430,left=66,right=40,top=24,bottom=48;
  const values=[];
  pts.forEach(r=>{values.push(Number(r.high),Number(r.low));});
  for(const v of [trade.entry_price,trade.exit_price,trade.stop_price,trade.target_price]) if(v!=null) values.push(Number(v));
  let min=Math.min(...values),max=Math.max(...values);
  const spread=(max-min)||1,pad=spread*.08;
  min-=pad;max+=pad;
  const X=i=>left+(i+.5)*(W-left-right)/pts.length;
  const Y=v=>top+(max-v)/(max-min)*(H-top-bottom);
  const cw=Math.max(5,((W-left-right)/pts.length)*.6);

  let svg=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none">`;
  for(let i=0;i<=6;i++){
    const v=min+(max-min)*i/6,yy=Y(v);
    svg+=`<line x1="${left}" y1="${yy}" x2="${W-right}" y2="${yy}" class="chart-gridline"/>`;
    svg+=`<text x="${left-9}" y="${yy+3}" text-anchor="end" class="chart-label">${v.toFixed(2)}</text>`;
  }

  pts.forEach((r,i)=>{
    const o=Number(r.open),c=Number(r.close),h=Number(r.high),l=Number(r.low),x=X(i);
    const up=c>=o,fill=up?"#148a5d":"#b6314d";
    svg+=`<title>${svgEscape(String(r.timestamp).slice(0,10))} · O ${o.toFixed(4)} · H ${h.toFixed(4)} · L ${l.toFixed(4)} · C ${c.toFixed(4)}</title>`;
    svg+=`<line x1="${x}" y1="${Y(h)}" x2="${x}" y2="${Y(l)}" stroke="#555" stroke-width="1"/>`;
    svg+=`<rect x="${x-cw/2}" y="${Math.min(Y(o),Y(c))}" width="${cw}" height="${Math.max(1,Math.abs(Y(o)-Y(c)))}" rx="1.5" fill="${fill}" opacity=".86"/>`;
  });

  if(showEma){
    for(const key of ["ema20","ema50"]){
      let d="";
      pts.forEach((r,i)=>{
        if(r[key]==null)return;
        d+=d?` L ${X(i)} ${Y(Number(r[key]))}`:`M ${X(i)} ${Y(Number(r[key]))}`;
      });
      if(d){
        const stroke=key==="ema20"?"#2c69b8":"#111";
        svg+=`<path d="${d}" fill="none" stroke="${stroke}" stroke-width="2"/>`;
      }
    }
  }

  const horizontal=(label,value,stroke)=>{
    if(value==null)return;
    const y=Y(Number(value));
    svg+=`<line x1="${left}" y1="${y}" x2="${W-right}" y2="${y}" stroke="${stroke}" stroke-width="1.4" stroke-dasharray="7 5"/>`;
    svg+=`<text x="${W-right}" y="${Math.max(top+9,y-5)}" text-anchor="end" class="chart-value">${label} ${Number(value).toFixed(4)}</text>`;
  };
  horizontal("ENTRY",trade.entry_price,"#2c69b8");
  horizontal("EXIT",trade.exit_price,"#111");
  horizontal("SL",trade.stop_price,"#b6314d");
  horizontal("TP",trade.target_price,"#148a5d");

  const ei=findClosestIndex(pts,trade.entry_time),xi=findClosestIndex(pts,trade.exit_time);
  if(ei!=null){
    const x=X(ei);
    svg+=`<line x1="${x}" y1="${top}" x2="${x}" y2="${H-bottom}" stroke="#2c69b8" stroke-width="1" stroke-dasharray="4 4"/>`;
    svg+=`<text x="${x+5}" y="${top+11}" class="chart-value">ENTRY</text>`;
  }
  if(xi!=null){
    const x=X(xi);
    svg+=`<line x1="${x}" y1="${top}" x2="${x}" y2="${H-bottom}" stroke="#111" stroke-width="1" stroke-dasharray="4 4"/>`;
    svg+=`<text x="${x+5}" y="${top+25}" class="chart-value">EXIT</text>`;
  }

  if(ei!=null&&xi!=null){
    const a=X(Math.min(ei,xi))-cw/2,b=X(Math.max(ei,xi))+cw/2;
    svg+=`<rect x="${a}" y="${top}" width="${Math.max(1,b-a)}" height="${H-top-bottom}" fill="#111" opacity=".045"/>`;
    svg+=`<text x="${(a+b)/2}" y="${top+10}" text-anchor="middle" class="chart-value">${trade.side==="SHORT"?"SHORT WINDOW":"LONG WINDOW"}</text>`;
  }

  const every=Math.max(1,Math.floor(pts.length/9));
  pts.forEach((r,i)=>{
    if(i%every!==0)return;
    svg+=`<text x="${X(i)}" y="${H-18}" text-anchor="middle" class="chart-label">${svgEscape(String(r.timestamp).slice(0,10))}</text>`;
  });
  svg+=`<text x="${left}" y="${top-8}" class="chart-label">${esc(trade.symbol||"")} · ${esc(trade.side||"")} · #${esc(trade.trade_id)}</text>`;
  svg+="</svg>";
  $("tradePriceMap").innerHTML=svg;
}

function clearTradeDetail(){
  $("tradePriceMap").innerHTML='<div class="trade-empty">Bir trade seçin.</div>';
  $("tradeSummary").innerHTML="";
  $("tradeLevels").innerHTML="";
  $("selectedTradeTitle").textContent="None";
  $("selectedTradeMeta").textContent="Tablodan bir trade satırına tıklayın.";
  $("selectedEntryContext").textContent="—";
  $("selectedExecutionContext").textContent="—";
}

function renderTradeDetail(x){
  renderTradeSummary(x);
  $("selectedTradeTitle").textContent=`${x.symbol||""} · Trade #${x.trade_id}`;
  $("selectedTradeMeta").textContent=`${x.side||"—"} · ${short(x.entry_time,40)} → ${short(x.exit_time,40)} · ${x.bars_held??"—"} bars · ${tradeOutcome(x)}`;
  $("selectedEntryContext").textContent=`Signal: ${x.entry_signal||"—"} · Score: ${x.entry_score==null?"—":Number(x.entry_score).toFixed(3)} · Reason: ${short(x.entry_reason||"—",260)}`;
  $("selectedExecutionContext").textContent=`Entry ${x.entry_price==null?"—":Number(x.entry_price).toFixed(4)} · Exit ${x.exit_price==null?"—":Number(x.exit_price).toFixed(4)} · SL ${x.stop_price==null?"—":Number(x.stop_price).toFixed(4)} · TP ${x.target_price==null?"—":Number(x.target_price).toFixed(4)} · Net ${x.net_pnl==null?"—":Number(x.net_pnl).toFixed(2)} · ${x.exit_reason||"—"}`;
}


function validationMetricState(v){
  const n=Number(v);
  if(!Number.isFinite(n)) return {cls:'na',pct:null};
  const pctv=Math.max(0,Math.min(100,n*100));
  return {cls:n>=0.70?'good':n>=0.45?'mid':'bad',pct:pctv};
}
function cockpitMetric(v){return v==null||!Number.isFinite(Number(v))?'N/A':pct(v);}
function cockpitTagClass(decision){const d=String(decision||'').toUpperCase();if(d.includes('APPROVE')||d.includes('ACCEPT'))return 'safe';if(d.includes('WEAK')||d.includes('REVIEW')||d.includes('DEPRIORITIZE'))return 'warn';if(d.includes('REJECT')||d.includes('FAIL')||d.includes('CONTRADICT'))return 'bad';return 'info';}
function renderDecisionCockpit(s){
  const pipeline=s.pipeline?.strategy||{}, ranking=pipeline.ranking||{}, rev=s.strategy_review?.row||{}, dec=s.final_decision?.decision||{}, cons=s.consolidation?.summary||{}, learn=s.learning?.ranking||{};
  const decision=dec.decision||'—', action=dec.action||'—', review=rev.verdict||'—';
  const available=[ranking.wfo_positive_ratio,ranking.cross_symbol_positive_ratio,ranking.cost_survival,ranking.parameter_stability,ranking.regime_stability].filter(v=>Number.isFinite(Number(v))).length;
  const evidenceRecords=Number(cons.evidence_records||0);
  $('cockpitDecision').textContent=decision;$('cockpitDecisionSub').textContent=cons.verified===false?'Verification NOT VERIFIED':'Decision record present';
  $('cockpitAction').textContent=action;$('cockpitActionSub').textContent=cons.next_research_question||learn.next_research_question||'—';
  $('cockpitReview').textContent=review;$('cockpitReviewSub').textContent=rev.score==null?'score unavailable':`score ${Number(rev.score).toFixed(3)}`;
  $('cockpitEvidence').textContent=evidenceRecords?num(evidenceRecords):'N/A';$('cockpitEvidenceSub').textContent=`${available}/5 robustness metrics available`;
  $('cockpitTag').textContent=decision;$('cockpitTag').className='tag '+cockpitTagClass(decision);
  $('cockpitFlowReview').textContent=review;
  $('cockpitFlowRobustness').textContent=available===0?'No numeric metrics':`${available}/5 metrics available`;
  $('cockpitFlowEvidence').textContent=cons.verified===false?'NOT VERIFIED':String(cons.verified??'—');
  $('cockpitFlowDecision').textContent=decision;
  $('cockpitFlowNext').textContent=short(cons.next_research_question||learn.next_research_question||action||'—',80);
  $('cockpitVerification').textContent=cons.verified===false?'NOT_VERIFIED':String(cons.verified??'—');
  $('cockpitConsistency').textContent=cons.cross_time_consistency||'—';
  const flag=$('cockpitEvidenceFlag');
  const verified=cons.verified===true, holdoutKnown=cons.holdout_positive!=null&&cons.holdout_total!=null;
  flag.className='cockpit-flag '+(verified&&holdoutKnown?'good':cons.verified===false?'bad':'warn');
  flag.textContent=verified? (holdoutKnown?'Verified evidence with explicit holdout counts.':'Verified snapshot; holdout counts unavailable.') : (cons.verified===false?'Current consolidation is not verified.':'Verification status is not explicit in the snapshot.');
  $('cockpitWfo').textContent=cockpitMetric(ranking.wfo_positive_ratio);$('cockpitCross').textContent=cockpitMetric(ranking.cross_symbol_positive_ratio);$('cockpitCost').textContent=cockpitMetric(ranking.cost_survival);$('cockpitParam').textContent=cockpitMetric(ranking.parameter_stability);$('cockpitRegime').textContent=cockpitMetric(ranking.regime_stability);
  $('cockpitHoldout').textContent=cons.holdout_positive==null||cons.holdout_total==null?'N/A':`${num(cons.holdout_positive)} / ${num(cons.holdout_total)}`;
  const whyParts=[];
  if(review!=='—')whyParts.push(`Review=${review}${rev.score==null?'':` (score ${Number(rev.score).toFixed(3)})`}`);
  if(available)whyParts.push(`${available}/5 robustness metrics are numerically available`);
  if(cons.cross_time_consistency)whyParts.push(`Cross-time consistency=${cons.cross_time_consistency}`);
  if(cons.verified!==undefined)whyParts.push(`Verified=${cons.verified===true?'YES':cons.verified===false?'NO':'UNKNOWN'}`);
  if(action!=='—')whyParts.push(`Action=${action}`);
  $('cockpitWhy').textContent=whyParts.length?whyParts.join(' · '):'Decision context unavailable in current snapshot.';
  $('cockpitQuestion').textContent=cons.next_research_question||learn.next_research_question||'Yeni araştırma sorusu bulunamadı.';
  $('cockpitMeta').textContent=`${pipeline.strategy_name||pipeline.strategy_id||'Strategy'} · ${evidenceRecords?num(evidenceRecords)+' evidence records · ':''}${available}/5 robustness metrics`;
}

function renderValidationBoard(s){
  const pipeline=s.pipeline?.strategy||{}, ranking=pipeline.ranking||{};
  const rev=s.strategy_review?.row||{}, decision=s.final_decision?.decision||{}, consolidation=s.consolidation?.summary||{};
  const metrics=[
    ['WFO positive',ranking.wfo_positive_ratio,'walk-forward'],
    ['Cross symbol',ranking.cross_symbol_positive_ratio,'cross-symbol consistency'],
    ['Cost survival',ranking.cost_survival,'cost robustness'],
    ['Parameter stability',ranking.parameter_stability,'parameter stability'],
    ['Regime stability',ranking.regime_stability,'regime stability']
  ];
  const available=metrics.filter(x=>Number.isFinite(Number(x[1]))).length;
  $('validationMeta').textContent=`${available}/5 robustness metrics available`;
  const worst=metrics.filter(x=>Number.isFinite(Number(x[1]))).reduce((m,x)=>m==null?Number(x[1]):Math.min(m,Number(x[1])),null);
  const gate=decision.decision||rev.verdict||'NO GATE';
  $('validationGate').textContent=gate;
  $('validationGate').className='tag '+(worst==null?'warn':worst>=0.70?'safe':worst>=0.45?'warn':'bad');
  $('validationMatrixMeta').textContent=worst==null?'No numeric robustness data':`weakest ${pct(worst)}`;
  $('validationMatrix').innerHTML=metrics.map(([label,value,note])=>{
    const st=validationMetricState(value);
    const display=value==null||!Number.isFinite(Number(value))?'N/A':pct(value);
    return `<div class="validation-metric ${st.cls}"><div class="vm-head"><span class="vm-label">${esc(label)}</span><span class="tag ${st.cls==='good'?'safe':st.cls==='mid'?'warn':st.cls==='bad'?'bad':'info'}">${st.cls==='na'?'N/A':st.cls.toUpperCase()}</span></div><div class="vm-value">${display}</div><div class="vm-note">${esc(note)}</div><div class="vm-bar"><div class="vm-fill" style="width:${st.pct==null?0:st.pct}%"></div></div></div>`;
  }).join('');

  $('valEvidenceRecords').textContent=num(consolidation.evidence_records);
  $('valSymbolRuns').textContent=num(consolidation.symbol_runs_combined);
  $('valPositiveRuns').textContent=num(consolidation.positive_full_runs);
  $('valNegativeRuns').textContent=num(consolidation.negative_full_runs);
  $('valPooledPositive').textContent=pct(consolidation.pooled_positive_ratio);
  $('valHoldout').textContent=consolidation.holdout_positive==null||consolidation.holdout_total==null?'N/A':`${num(consolidation.holdout_positive)} / ${num(consolidation.holdout_total)}`;

  $('valReviewVerdict').textContent=rev.verdict||'—';
  $('valReviewScore').textContent=rev.score==null?'—':Number(rev.score).toFixed(3);
  $('valFinalDecision').textContent=decision.decision||'—';
  $('valDecisionAction').textContent=decision.action||'—';
  $('valVerification').textContent=`Verification: ${consolidation.verified===false?'NOT_VERIFIED':String(consolidation.verified??'—')} · consistency: ${consolidation.cross_time_consistency||'—'}`;
  $('validationNextQuestion').textContent=consolidation.next_research_question||s.learning?.ranking?.next_research_question||'Yeni araştırma sorusu bulunamadı.';
}

function renderStrategy(s){
 const p=s.pipeline?.strategy||{},r=p.ranking||{},rev=s.strategy_review?.row||{},d=s.final_decision?.decision||{},lr=s.learning?.ranking||{};
 $("strategyId").textContent=p.strategy_id||"—";$("strategyName").textContent=p.strategy_name||"—";$("strategyClass").textContent=r.classification||"—";
 $("verdictTag").textContent=rev.verdict||"NO REVIEW";$("decision").textContent=d.decision||"—";$("decisionAction").textContent=d.action||"—";
 $("v6").textContent=r.score==null?"—":Number(r.score).toFixed(4);$("cross").textContent=pct(r.cross_symbol_positive_ratio);$("cost").textContent=pct(r.cost_survival);$("param").textContent=pct(r.parameter_stability);$("regime").textContent=pct(r.regime_stability);$("wfo").textContent=pct(r.wfo_positive_ratio);
 $("nextQuestion").textContent=s.consolidation?.summary?.next_research_question||lr.next_research_question||"—";
 $("consStatus").textContent=s.consolidation?.available?"AVAILABLE":"MISSING";
 $("reviewMethod").textContent=rev.review_method||"—";$("reviewVerdict").textContent=rev.verdict||"—";$("reviewScore").textContent="score "+(rev.score==null?"—":Number(rev.score).toFixed(3));
 $("reviewReasoning").textContent=short(rev.normalized_reasoning||rev.reasoning||rev.review_text||rev.review_reasoning||"Review reasoning yok.",900);
}
function renderEvidence(s){
 const c=s.consolidation?.summary||{};
 $("eRecords").textContent=num(c.evidence_records);$("eRuns").textContent=num(c.symbol_runs_combined);$("ePos").textContent=num(c.positive_full_runs);$("eNeg").textContent=num(c.negative_full_runs);
 $("pooled").textContent=pct(c.pooled_positive_ratio);$("holdout").textContent=c.holdout_positive==null||c.holdout_total==null?"NOT_AVAILABLE":`${num(c.holdout_positive)} / ${num(c.holdout_total)}`;
 $("interpretation").textContent=`${c.cross_time_consistency||"—"} · review=${c.strategy_review_verdict||"—"} · verified=${c.verified===false?"NOT_VERIFIED":String(c.verified??"—")}`;
}
function symbolStatus(x){
 if(x.positive===true)return "POSITIVE";
 if(x.positive===false)return "NEGATIVE";
 if(x.return_percent!=null)return Number(x.return_percent)>=0?"POSITIVE":"NEGATIVE";
 return "UNKNOWN";
}
function renderSymbols(ex){
 const sets=ex.datasets||[];let rows=[];let names=new Set();let positive=0,negative=0;let counts={};
 for(const ds of sets){
   counts[ds.source]=(ds.records||[]).length;
   for(const x of (ds.records||[])){
     const st=symbolStatus(x);names.add(x.symbol);if(st==="POSITIVE")positive++;if(st==="NEGATIVE")negative++;
     rows.push({...x,source:ds.source,status:st});
   }
 }
 $("v6Count").textContent=num(counts.V6_PIPELINE||0);$("oldCount").textContent=num(counts.INDEPENDENT_OLD||0);$("freshCount").textContent=num(counts.INDEPENDENT_FRESH||0);$("uniqueCount").textContent=num(names.size);$("positiveKnown").textContent=num(positive);$("negativeKnown").textContent=num(negative);$("symbolMeta").textContent=`${num(rows.length)} record`;
 $("symbolTable").innerHTML=rows.length?rows.map(x=>`<tr><td>${esc(x.source)}</td><td><strong>${esc(x.symbol)}</strong></td><td>${x.return_percent==null?"—":n2(x.return_percent)}</td><td>${x.profit_factor==null?"—":n2(x.profit_factor)}</td><td>${x.trades==null?"—":num(x.trades)}</td><td>${x.win_rate_percent==null?"—":n2(x.win_rate_percent)+"%"}</td><td>${x.max_drawdown_percent==null?"—":n2(x.max_drawdown_percent)+"%"}</td><td><span class="tag ${x.status==="POSITIVE"?"safe":x.status==="NEGATIVE"?"bad":"warn"}">${esc(x.status)}</span></td></tr>`).join(""):`<tr><td colspan="8">Symbol-level kayıt bulunamadı.</td></tr>`;
}
function renderBrain(b){
 $("strategyReviews").innerHTML=(b.recent_strategy_reviews||[]).slice(0,6).map(x=>`<div class="row"><div class="rowtop"><span class="tag ${x.verdict==="PARTIALLY_SUPPORTIVE"?"warn":x.verdict==="CONTRADICTORY"?"bad":"safe"}">${esc(x.verdict||"REVIEW")}</span><strong>${esc(x.strategy_id||"—")}</strong><span class="right">${x.score==null?"—":"score "+Number(x.score).toFixed(3)}</span></div><div class="desc">${esc(short(x.reasoning||x.review_text||x.review_reasoning||x.review_method||""))}</div></div>`).join("")||`<div class="muted">Review kaydı yok.</div>`;
 $("researchQueue").innerHTML=(b.recent_queue||[]).slice(0,6).map(x=>`<div class="row"><div class="rowtop"><span class="tag info">${esc(x.status||"—")}</span><strong>${esc(short(x.question||"Research task",100))}</strong><span class="right">P${esc(x.priority??"—")}</span></div></div>`).join("")||`<div class="muted">Research queue kaydı yok.</div>`;
}
function renderLearning(l){
 const rows=l.strategy_rankings||[];$("learningMeta").textContent=`${num(rows.length)} recent ranking`;
 $("learningTable").innerHTML=rows.length?rows.map(x=>`<tr><td>${esc(x.strategy_name||x.strategy_id||"—")}</td><td>${x.learning_score==null?"—":Number(x.learning_score).toFixed(4)}</td><td>${esc(x.action||"—")}</td><td>${esc(x.verification_status||"—")}</td><td>${esc(x.candidate_status||"—")}</td><td>${esc(short(x.reason||"—",150))}</td></tr>`).join(""):`<tr><td colspan="6">Learning ranking kaydı yok.</td></tr>`;
}
function renderDB(d){
 const f=d.schema_freeze||{};$("freeze").textContent=f.contract_status||"—";$("freezeHash").textContent=f.contract_hash?"hash "+f.contract_hash:"—";$("dbMeta").textContent=d.available?"DB AVAILABLE":"DB UNAVAILABLE";
}

// =========================================================
// TRADINGVIEW RESEARCH CHART
// =========================================================
let tvResearchChart=null;let tvResearchCandleSeries=null;let tvResearchEma20=null;let tvResearchEma50=null;let tvResearchVolumeSeries=null;let tvResearchMarkers=null;let tvResearchSelectedTradePath=null;let tvResearchEmaEnabled=true;let tvResearchSignalsEnabled=true;let tvResearchZonesEnabled=true;let tvResearchTradePathEnabled=true;let tvResearchSignalEvents=[];let tvResearchRows=[];let tvResearchResizeObserver=null;let tvResearchPriceLines=[];let tvSelectedChartPayload=null;let tvPendingTradeSelection=null;let tvSignalTooltipVisible=false;let tvResearchScope=null;
function tvSafeDate(value){const text=String(value||"").trim();if(!text)return null;const date=text.slice(0,10);return /^\\d{4}-\\d{2}-\\d{2}$/.test(date)?date:null;}
function tvNumber(value){const n=Number(value);return Number.isFinite(n)?n:null;}
function tvClosestDate(rows,target){const wanted=tvSafeDate(target);if(!wanted||!rows.length)return null;let best=null,bestDistance=Infinity;const targetMs=Date.parse(wanted+"T00:00:00Z");for(const row of rows){const date=tvSafeDate(row.timestamp);if(!date)continue;const distance=Math.abs(Date.parse(date+"T00:00:00Z")-targetMs);if(distance<bestDistance){bestDistance=distance;best=date;}}return best;}
function tvGetMatchingTrades(symbol){const normalized=String(symbol||"").trim().toUpperCase();const rows=[];for(const dataset of (tradeData?.datasets||[])){for(const trade of (dataset?.trades||[])){const tradeSymbol=String(trade?.symbol||"").trim().toUpperCase();if(tradeSymbol===normalized||tradeSymbol.replace(/\\.IS$/i,"")===normalized.replace(/\\.IS$/i,""))rows.push(trade);}}return rows;}
function updateTvResearchInfo(data){const symbol=data?.resolved_symbol||data?.symbol||$("tvSymbol")?.value||"—";const source=data?.source||"—";const bars=Number(data?.bars||data?.rows?.length||0);$("tvInfoSymbol").textContent=symbol;$("tvInfoRange").textContent=`${data?.start?String(data.start).slice(0,10):"—"} → ${data?.end?String(data.end).slice(0,10):"—"}`;$("tvInfoSource").textContent=source;$("tvInfoBars").textContent=`${num(bars)} historical bars · ${data?.read_only===true?"read-only":"—"}`;$("tvChartMeta").textContent=`${symbol} · ${data?.interval||"1d"} · ${num(bars)} bars · ${source}`;}
function tvFmtPrice(value){const n=Number(value);return Number.isFinite(n)?n.toLocaleString("tr-TR",{minimumFractionDigits:2,maximumFractionDigits:4}):"—";}
function tvSafeDate(value){const text=String(value||"").trim();if(!text)return null;const date=text.slice(0,10);return /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(date)?date:null;}
function tvNumber(value){const n=Number(value);return Number.isFinite(n)?n:null;}
function tvClosestDate(rows,target){const wanted=tvSafeDate(target);if(!wanted||!rows.length)return null;let best=null,bestDistance=Infinity;const targetMs=Date.parse(wanted+"T00:00:00Z");for(const row of rows){const date=tvSafeDate(row.timestamp);if(!date)continue;const distance=Math.abs(Date.parse(date+"T00:00:00Z")-targetMs);if(distance<bestDistance){bestDistance=distance;best=date;}}return best;}
function tvGetMatchingTrades(symbol){const normalized=String(symbol||"").trim().toUpperCase();const rows=[];for(const dataset of (tradeData?.datasets||[])){for(const trade of (dataset?.trades||[])){const tradeSymbol=String(trade?.symbol||"").trim().toUpperCase();if(tradeSymbol===normalized||tradeSymbol.replace(/\\.IS$/i,"")===normalized.replace(/\\.IS$/i,""))rows.push(trade);}}return rows;}
function updateTvResearchInfo(data){const symbol=data?.resolved_symbol||data?.symbol||$("tvSymbol")?.value||"—";const source=data?.source||"—";const bars=Number(data?.bars||data?.rows?.length||0);$("tvInfoSymbol").textContent=symbol;$("tvInfoRange").textContent=`${data?.start?String(data.start).slice(0,10):"—"} → ${data?.end?String(data.end).slice(0,10):"—"}`;$("tvInfoSource").textContent=source;$("tvInfoBars").textContent=`${num(bars)} historical bars · ${data?.read_only===true?"read-only":"—"}`;$("tvChartMeta").textContent=`${symbol} · ${data?.interval||"1d"} · ${num(bars)} bars · ${source}`;$("tvLegendSymbol").textContent=`${symbol} · ${(data?.interval||"1d").toUpperCase()}`;}
function clearTvPriceLines(){if(!tvResearchCandleSeries)return;for(const line of tvResearchPriceLines){try{tvResearchCandleSeries.removePriceLine(line)}catch(e){}}tvResearchPriceLines=[];}
function tvAddPriceLine(price,title,color,lineStyle){if(!tvResearchCandleSeries||price==null||!Number.isFinite(Number(price)))return;const line=tvResearchCandleSeries.createPriceLine({price:Number(price),color,title,axisLabelVisible:true,lineVisible:true,lineWidth:1,lineStyle});tvResearchPriceLines.push(line);}
function tvNormalizeResearchScope(scope){const s=scope||{};return {trainStart:s.trainStart||s.train_start||s.trainFrom||s.train_from||null,trainEnd:s.trainEnd||s.train_end||s.trainTo||s.train_to||null,validationStart:s.validationStart||s.validation_start||s.validationFrom||s.validation_from||null,validationEnd:s.validationEnd||s.validation_end||s.validationTo||s.validation_to||null,independentStart:s.independentStart||s.independent_start||s.independentFrom||s.independent_from||s.testStart||s.test_start||null,independentEnd:s.independentEnd||s.independent_end||s.independentTo||s.independent_to||s.testEnd||s.test_end||null};}
function tvExtractResearchScope(){if(tvResearchScope&&Object.values(tvNormalizeResearchScope(tvResearchScope)).some(Boolean))return tvNormalizeResearchScope(tvResearchScope);for(const event of tvResearchSignalEvents||[]){const scope=event?.provenance?.experiment?.scope||event?.provenance?.scope;if(scope)return tvNormalizeResearchScope(scope);}return tvNormalizeResearchScope(null);}
function tvResearchScopeSegments(){const s=tvExtractResearchScope();return [{key:"train",label:"TRAIN",start:tvClosestDate(tvResearchRows,s.trainStart),end:tvClosestDate(tvResearchRows,s.trainEnd)},{key:"validation",label:"VALIDATION",start:tvClosestDate(tvResearchRows,s.validationStart),end:tvClosestDate(tvResearchRows,s.validationEnd)},{key:"independent",label:"INDEPENDENT",start:tvClosestDate(tvResearchRows,s.independentStart),end:tvClosestDate(tvResearchRows,s.independentEnd)}].filter(x=>x.start&&x.end);}
function tvUpdateResearchZones(){const layer=$("tvResearchZones");if(!layer||!tvResearchChart)return;layer.innerHTML="";if(!tvResearchZonesEnabled)return;for(const seg of tvResearchScopeSegments()){let x1=null,x2=null;try{x1=tvResearchChart.timeScale().timeToCoordinate(seg.start);x2=tvResearchChart.timeScale().timeToCoordinate(seg.end);}catch(e){}if(x1==null&&x2==null)continue;const a=Math.min(x1??x2,x2??x1),b=Math.max(x1??x2,x2??x1);const left=Math.max(0,a),right=Math.min(layer.clientWidth,b);if(right<=left)continue;const el=document.createElement("div");el.className=`tv-zone ${seg.key}`;el.style.left=`${left}px`;el.style.width=`${Math.max(2,right-left)}px`;el.innerHTML=`<div class="tv-zone-label">${seg.label}</div>`;layer.appendChild(el);}}
function tvDrawSelectionLines(payload){clearTvPriceLines();tvClearSelectedTradePath();tvSetFocusBadge(payload);if(!payload){$("tvLegendSelected").textContent="No selection";return;}if(payload.type==="RESEARCH"){const e=payload.event||{};const type=String(e.eventType||e.signal||e.action||"SIGNAL").toUpperCase();const isBuy=type.includes("BUY")||type.includes("ENTRY")||type.includes("LONG");const color=isBuy?"#3aa6ff":"#ff5b72";if(e.price!=null)tvAddPriceLine(e.price,isBuy?"BUY":"EXIT",color,LightweightCharts.LineStyle.Dashed);$("tvLegendSelected").textContent=`${isBuy?"BUY":"EXIT"} · ${tvSafeDate(e.timestamp||e.time||e.date)||"—"}`;return;}const t=payload.trade||{};if(t.entry_price!=null)tvAddPriceLine(t.entry_price,"ENTRY","#3aa6ff",LightweightCharts.LineStyle.Solid);if(t.exit_price!=null)tvAddPriceLine(t.exit_price,"EXIT","#ff5b72",LightweightCharts.LineStyle.Solid);if(t.sl!=null)tvAddPriceLine(t.sl,"SL","#ff5b72",LightweightCharts.LineStyle.Dashed);if(t.tp!=null)tvAddPriceLine(t.tp,"TP","#35c98b",LightweightCharts.LineStyle.Dashed);tvDrawSelectedTradePath(t);$("tvLegendSelected").textContent=`Trade #${t.trade_id??"—"} · ${payload.side||"—"}`;}
function tvFocusTrade(trade){if(!tvResearchChart||!trade)return;const entry=tvClosestDate(tvResearchRows,trade.entry_time),exit=tvClosestDate(tvResearchRows,trade.exit_time);if(!entry&&!exit)return;const a=entry||exit,b=exit||entry;const ai=tvResearchRows.findIndex(x=>tvSafeDate(x.timestamp)===a);const bi=tvResearchRows.findIndex(x=>tvSafeDate(x.timestamp)===b);if(ai<0&&bi<0)return;const lo=Math.max(0,Math.min(ai<0?bi:ai,bi<0?ai:bi)-24);const hi=Math.min(tvResearchRows.length-1,Math.max(ai<0?bi:ai,bi<0?ai:bi)+24);try{tvResearchChart.timeScale().setVisibleLogicalRange({from:lo,to:hi});}catch(e){}}
function updateTvLegendAtRow(row){const el=(id)=>$(id);if(!row){return;}el("tvLegendTime").textContent=tvSafeDate(row.timestamp)||"—";el("tvLegendOpen").textContent=tvFmtPrice(row.open);el("tvLegendHigh").textContent=tvFmtPrice(row.high);el("tvLegendLow").textContent=tvFmtPrice(row.low);el("tvLegendClose").textContent=tvFmtPrice(row.close);el("tvLegendVolume").textContent=Number.isFinite(Number(row.volume))?Number(row.volume).toLocaleString("tr-TR",{maximumFractionDigits:0}):"—";el("tvLegendEma20").textContent=tvFmtPrice(row.ema20);el("tvLegendEma50").textContent=tvFmtPrice(row.ema50);}
function destroyTvResearchChart(){clearTvPriceLines();if(tvResearchResizeObserver){try{tvResearchResizeObserver.disconnect()}catch(e){}}if(tvResearchChart){try{tvResearchChart.remove()}catch(e){}}tvResearchResizeObserver=null;tvResearchChart=null;tvResearchCandleSeries=null;tvResearchEma20=null;tvResearchEma50=null;tvResearchVolumeSeries=null;tvResearchMarkers=null;}
function buildTvCandleData(rows){const seen=new Set(),output=[];for(const row of rows||[]){const time=tvSafeDate(row.timestamp),open=tvNumber(row.open),high=tvNumber(row.high),low=tvNumber(row.low),close=tvNumber(row.close);if(!time||open===null||high===null||low===null||close===null||seen.has(time))continue;seen.add(time);output.push({time,open,high,low,close});}return output.sort((a,b)=>String(a.time).localeCompare(String(b.time)));}
function buildTvLineData(rows,key){const seen=new Set(),output=[];for(const row of rows||[]){const time=tvSafeDate(row.timestamp),value=tvNumber(row[key]);if(!time||value===null||seen.has(time))continue;seen.add(time);output.push({time,value});}return output.sort((a,b)=>String(a.time).localeCompare(String(b.time)));}
function buildTvVolumeData(rows){const seen=new Set(),output=[];for(const row of rows||[]){const time=tvSafeDate(row.timestamp),volume=tvNumber(row.volume),open=tvNumber(row.open),close=tvNumber(row.close);if(!time||volume===null||seen.has(time))continue;seen.add(time);output.push({time,value:volume,color:(close!=null&&open!=null&&close>=open)?"rgba(54,201,143,.38)":"rgba(255,91,114,.38)"});}return output.sort((a,b)=>String(a.time).localeCompare(String(b.time)));}
function buildTvTradeFallbackMarkers(symbol){const markers=[],seen=new Set();for(const trade of tvGetMatchingTrades(symbol)){const entryTime=tvClosestDate(tvResearchRows,trade.entry_time),exitTime=tvClosestDate(tvResearchRows,trade.exit_time);if(entryTime&& !seen.has(`B:${entryTime}`)){markers.push({time:entryTime,position:"belowBar",shape:"arrowUp",color:"#3aa6ff",text:"BUY"});seen.add(`B:${entryTime}`);}if(exitTime&& !seen.has(`E:${exitTime}`)){markers.push({time:exitTime,position:"aboveBar",shape:"arrowDown",color:"#ff5b72",text:"EXIT"});seen.add(`E:${exitTime}`);}}markers.sort((a,b)=>String(a.time).localeCompare(String(b.time)));return markers;}
function buildTvResearchSignalMarkers(){if(!tvResearchSignalsEnabled||!tvResearchSignalEvents.length)return[];const markers=[],seen=new Set();for(const event of tvResearchSignalEvents){const date=tvClosestDate(tvResearchRows,event.timestamp||event.time||event.date);if(!date)continue;const type=String(event.eventType||event.signal||event.action||"").toUpperCase();const isBuy=type.includes("BUY")||type.includes("ENTRY")||type.includes("LONG");const isSell=type.includes("SELL")||type.includes("EXIT")||type.includes("SHORT");if(!isBuy&&!isSell)continue;const key=`${isBuy?"B":"E"}:${date}`;if(seen.has(key))continue;seen.add(key);markers.push({time:date,position:isBuy?"belowBar":"aboveBar",shape:isBuy?"arrowUp":"arrowDown",color:isBuy?"#3aa6ff":"#ff5b72",text:isBuy?"BUY":"EXIT"});}markers.sort((a,b)=>String(a.time).localeCompare(String(b.time)));return markers;}
function buildTvActiveMarkers(symbol){const research=buildTvResearchSignalMarkers();return research.length?research:buildTvTradeFallbackMarkers(symbol);}
function tvFindEventAtTime(time){const target=String(time||"");for(const event of tvResearchSignalEvents){const d=tvClosestDate(tvResearchRows,event.timestamp||event.time||event.date);if(d===target)return event;}return null;}
function tvFindTradeAtTime(symbol,time){const target=String(time||"");for(const trade of tvGetMatchingTrades(symbol)){const entry=tvClosestDate(tvResearchRows,trade.entry_time),exit=tvClosestDate(tvResearchRows,trade.exit_time);if(entry===target)return {trade,side:"ENTRY"};if(exit===target)return {trade,side:"EXIT"};}return null;}
function tvCompact(value,fallback='—'){if(value===null||value===undefined||value==='')return fallback;if(typeof value==='object'){try{return JSON.stringify(value)}catch(e){return fallback}}return String(value);}function tvHideSignalTooltip(){const el=$("tvSignalTooltip");if(el){el.hidden=true;el.innerHTML="";}tvSignalTooltipVisible=false;}
function tvShowSignalTooltip(payload,x,y){const el=$("tvSignalTooltip");if(!el||!payload)return;const trade=payload.type==="TRADE"?(payload.trade||{}):null;const event=payload.type==="RESEARCH"?(payload.event||{}):null;const type=payload.type==="TRADE"?String(payload.side||"TRADE").toUpperCase():String(event?.eventType||event?.signal||event?.action||"SIGNAL").toUpperCase();const date=payload.type==="TRADE"?(payload.side==="ENTRY"?trade.entry_time:trade.exit_time):(event?.timestamp||event?.time||event?.date);const price=payload.type==="TRADE"?(payload.side==="ENTRY"?trade.entry_price:trade.exit_price):event?.price;const symbol=payload.type==="TRADE"?(trade.symbol||$("tvSymbol")?.value||"—"):(event?.symbol||$("tvSymbol")?.value||"—");const pnl=trade?.net_pnl;const entry=tvNumber(trade?.entry_price),exit=tvNumber(trade?.exit_price);let ret=null;if(entry!=null&&exit!=null&&entry!==0){const side=String(trade?.side||"LONG").toUpperCase();ret=((exit-entry)/entry)*(side.includes("SHORT")?-1:1)*100;}const signalId=event?.signalId||event?.id;const tradeId=trade?.trade_id;const score=event?.score;el.innerHTML=`<div class="tt-head">${esc(type)} · ${esc(symbol)}</div><div class="tt-sub">${esc(tvSafeDate(date)||tvCompact(date))}</div><div class="tt-grid"><div><div class="tt-k">Price</div><div class="tt-v">${esc(tvFmtPrice(price))}</div></div><div><div class="tt-k">Event</div><div class="tt-v">${esc(payload.type==="TRADE"?`Trade #${tradeId??"—"}`:(signalId||"Signal"))}</div></div>${pnl!=null?`<div><div class="tt-k">PnL</div><div class="tt-v">${esc(Number(pnl).toFixed(2))}</div></div>`:""}${ret!=null?`<div><div class="tt-k">Return</div><div class="tt-v">${esc(ret.toFixed(2)+"%")}</div></div>`:""}${score!=null?`<div><div class="tt-k">Score</div><div class="tt-v">${esc(Number(score).toFixed(3))}</div></div>`:""}${trade?.exit_reason?`<div><div class="tt-k">Exit</div><div class="tt-v">${esc(trade.exit_reason)}</div></div>`:""}</div>`;const host=$("tvResearchChart");const w=host?.clientWidth||0,h=host?.clientHeight||0;const left=Math.min(Math.max(10,(Number(x)||0)+14),Math.max(10,w-el.offsetWidth-10));const top=Math.min(Math.max(55,(Number(y)||0)+14),Math.max(55,h-el.offsetHeight-30));el.style.left=`${left}px`;el.style.top=`${top}px`;el.hidden=false;tvSignalTooltipVisible=true;}
function tvSetFocusBadge(payload){const el=$("tvFocusBadge");if(!el)return;if(!payload||payload.type!=="TRADE"){el.hidden=true;el.textContent="";return;}const t=payload.trade||{};const entry=tvNumber(t.entry_price),exit=tvNumber(t.exit_price);let ret=null;if(entry!=null&&exit!=null&&entry!==0){const side=String(t.side||"LONG").toUpperCase();ret=((exit-entry)/entry)*(side.includes("SHORT")?-1:1)*100;}el.textContent=`FOCUS · ${String(payload.side||"TRADE").toUpperCase()} · TRADE #${t.trade_id??"—"}${ret!=null?` · ${ret.toFixed(2)}%`:""}`;el.hidden=false;}
function tvDrawSelectedTradePath(trade){if(!tvResearchChart||!trade||!tvResearchTradePathEnabled)return;try{if(tvResearchSelectedTradePath){tvResearchChart.removeSeries(tvResearchSelectedTradePath);tvResearchSelectedTradePath=null;}const entry=tvClosestDate(tvResearchRows,trade.entry_time),exit=tvClosestDate(tvResearchRows,trade.exit_time);const ep=tvNumber(trade.entry_price),xp=tvNumber(trade.exit_price);if(!entry||!exit||ep==null||xp==null||entry===exit)return;tvResearchSelectedTradePath=tvResearchChart.addSeries(LightweightCharts.LineSeries,{color:String(trade?.side||"LONG").toUpperCase().includes("SHORT")?"#d8a94a":"#3aa6ff",lineWidth:3,lineStyle:LightweightCharts.LineStyle.Dashed,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});tvResearchSelectedTradePath.setData([{time:entry,value:ep},{time:exit,value:xp}]);}catch(e){}}
function tvClearSelectedTradePath(){if(tvResearchChart&&tvResearchSelectedTradePath){try{tvResearchChart.removeSeries(tvResearchSelectedTradePath)}catch(e){}tvResearchSelectedTradePath=null;}}

function tvRenderProvenance(provenance){const el=$("tvProvenance");if(!el)return;if(!provenance){el.textContent="Bu event için research lineage bulunamadı.";return;}const e=provenance.experiment||{},r=provenance.result||{},v=r.validation||{},d=provenance.decision||{},l=provenance.learning||{},scope=e.scope||{};const cell=(k,val,wide=false)=>`<div class="tv-provenance-item ${wide?'tv-provenance-wide':''}"><div class="k">${esc(k)}</div><div class="v">${esc(tvCompact(val))}</div></div>`;el.innerHTML=`<div class="tv-provenance-grid">${cell('Experiment ID',e.id)}${cell('Result ID',r.resultId)}${cell('Run ID',e.runId||r.runId)}${cell('Validation',r.validationStatus||v.status)}${cell('Decision',d.decision)}${cell('Decision Action',d.action)}${cell('Learning',l.action||l.candidate_status||l.verification_status)}${cell('Strategy',e.strategyName||e.strategyId)}${cell('Research Question',e.researchQuestion,true)}${cell('Rule Definition',e.ruleDefinition,true)}${cell('Train',`${tvCompact(scope.trainStart)} → ${tvCompact(scope.trainEnd)}`)}${cell('Validation Slice',`${tvCompact(scope.validationStart)} → ${tvCompact(scope.validationEnd)}`)}${cell('Independent Slice',`${tvCompact(scope.independentStart)} → ${tvCompact(scope.independentEnd)}`)}${cell('Validation Conclusion',v.conclusion,true)}</div>`;}
function showTvSelectedSignal(payload){tvSelectedChartPayload=payload;tvHideSignalTooltip();tvSetFocusBadge(payload);const titleEl=$("tvSelectedSignalTitle"),bodyEl=$("tvSelectedSignal");if(!titleEl||!bodyEl)return;if(!payload){titleEl.textContent="None";bodyEl.textContent="Grafikte bir BUY/EXIT işaretine tıklayın.";tvRenderProvenance(null);tvDrawSelectionLines(null);return;}if(payload.type==="RESEARCH"){const e=payload.event||{},type=String(e.eventType||e.signal||e.action||"SIGNAL").toUpperCase();titleEl.textContent=`${type} · ${e.symbol||$("tvSymbol")?.value||"—"}`;bodyEl.textContent=`${e.timestamp||e.time||"—"} · price=${e.price==null?"—":Number(e.price).toFixed(4)} · score=${e.score==null?"—":Number(e.score).toFixed(3)} · source=${e.source||"—"} · signalId=${e.signalId||"—"}`;tvRenderProvenance(e.provenance);tvDrawSelectionLines(payload);}else{const t=payload.trade||{};titleEl.textContent=`${payload.side} · ${t.symbol||"—"} · Trade #${t.trade_id??"—"}`;bodyEl.textContent=`${payload.side==="ENTRY"?t.entry_time:t.exit_time||"—"} · price=${payload.side==="ENTRY"?(t.entry_price??"—"):(t.exit_price??"—")} · PnL=${t.net_pnl==null?"—":Number(t.net_pnl).toFixed(2)} · reason=${t.exit_reason||"—"}`;tvRenderProvenance(payload.provenance||null);tvDrawSelectionLines(payload);tvFocusTrade(t);}titleEl.parentElement?.parentElement?.classList.add("tv-signal-selected");}
function createTvResearchChart(data){if(typeof LightweightCharts==="undefined")throw new Error("TradingView Lightweight Charts yüklenemedi.");const container=$("tvResearchChart");destroyTvResearchChart();tvHideSignalTooltip();container.innerHTML="";const chart=LightweightCharts.createChart(container,{autoSize:true,layout:{textColor:"#91a0af",background:{type:"solid",color:"#0b1015"}},grid:{vertLines:{color:"#18212a"},horzLines:{color:"#18212a"}},rightPriceScale:{borderColor:"#26313b",scaleMargins:{top:.06,bottom:.12}},timeScale:{borderColor:"#26313b",timeVisible:false,secondsVisible:false,barSpacing:7,minBarSpacing:3},crosshair:{mode:LightweightCharts.CrosshairMode.Normal,vertLine:{color:"#607080",width:1,style:LightweightCharts.LineStyle.Dashed,labelBackgroundColor:"#202a34"},horzLine:{color:"#607080",width:1,style:LightweightCharts.LineStyle.Dashed,labelBackgroundColor:"#202a34"}}});const candles=buildTvCandleData(data.rows);if(!candles.length)throw new Error("OHLCV verisi boş.");const candleSeries=chart.addSeries(LightweightCharts.CandlestickSeries,{upColor:"#36c98f",downColor:"#ff5b72",borderVisible:false,wickUpColor:"#36c98f",wickDownColor:"#ff5b72",priceLineVisible:true,lastValueVisible:true});candleSeries.setData(candles);const ema20=chart.addSeries(LightweightCharts.LineSeries,{color:"#3aa6ff",lineWidth:2,priceLineVisible:false,lastValueVisible:false});ema20.setData(buildTvLineData(data.rows,"ema20"));const ema50=chart.addSeries(LightweightCharts.LineSeries,{color:"#d8a94a",lineWidth:2,priceLineVisible:false,lastValueVisible:false});ema50.setData(buildTvLineData(data.rows,"ema50"));const volume=chart.addSeries(LightweightCharts.HistogramSeries,{priceFormat:{type:"volume"},priceScaleId:"volume",base:0});volume.setData(buildTvVolumeData(data.rows));chart.priceScale("volume").applyOptions({scaleMargins:{top:.82,bottom:0},borderVisible:false});const activeSymbol=data.resolved_symbol||data.symbol||"";const markerApi=LightweightCharts.createSeriesMarkers(candleSeries,buildTvActiveMarkers(activeSymbol));chart.subscribeClick((param)=>{const time=param?.time;if(time==null)return;const date=typeof time==="string"?time:new Date(Number(time)*1000).toISOString().slice(0,10);const event=tvFindEventAtTime(date);if(event){showTvSelectedSignal({type:"RESEARCH",event});return;}const trade=tvFindTradeAtTime(activeSymbol,date);if(trade)showTvSelectedSignal({type:"TRADE",...trade});});chart.subscribeCrosshairMove((param)=>{if(!param||param.time==null){if(!tvSelectedChartPayload)tvHideSignalTooltip();$("tvLegendSelected").textContent=tvSelectedChartPayload?$("tvLegendSelected").textContent:"No selection";return;}const candle=param.seriesData?.get(candleSeries);if(!candle)return;const row=tvResearchRows.find(r=>tvSafeDate(r.timestamp)===tvSafeDate(param.time));if(row)updateTvLegendAtRow(row);const date=typeof param.time==="string"?param.time:new Date(Number(param.time)*1000).toISOString().slice(0,10);const event=tvFindEventAtTime(date);const trade=event?null:tvFindTradeAtTime(activeSymbol,date);if(event){tvShowSignalTooltip({type:"RESEARCH",event},param.point?.x,param.point?.y);}else if(trade){tvShowSignalTooltip({type:"TRADE",...trade},param.point?.x,param.point?.y);}else if(!tvSelectedChartPayload){tvHideSignalTooltip();}});chart.timeScale().subscribeVisibleLogicalRangeChange(()=>{tvUpdateResearchZones();});tvResearchChart=chart;tvResearchCandleSeries=candleSeries;tvResearchEma20=ema20;tvResearchEma50=ema50;tvResearchVolumeSeries=volume;tvResearchMarkers=markerApi;tvResearchEma20.applyOptions({visible:tvResearchEmaEnabled});tvResearchEma50.applyOptions({visible:tvResearchEmaEnabled});chart.timeScale().fitContent();if(typeof ResizeObserver!=="undefined"){tvResearchResizeObserver=new ResizeObserver(()=>{if(tvResearchChart)tvResearchChart.resize(container.clientWidth,container.clientHeight);tvUpdateResearchZones();});tvResearchResizeObserver.observe(container);}if(tvPendingTradeSelection){const pending=tvPendingTradeSelection;tvPendingTradeSelection=null;showTvSelectedSignal({type:"TRADE",trade:pending,side:"ENTRY"});}else if(tvSelectedChartPayload){tvDrawSelectionLines(tvSelectedChartPayload);}const tradeCount=tvGetMatchingTrades(activeSymbol).length,markerCount=buildTvActiveMarkers(activeSymbol).length;$("tvChartStatus").textContent=`Loaded · ${candles.length} candles · ${markerCount} research markers`;$("tvInfoTrade").textContent=tradeCount?`${tradeCount} eşleşen trade kaydı mevcut.`:"Bu sembol için eşleşen trade kaydı bulunamadı.";$("tvInfoSignals").textContent=tvResearchSignalEvents.length?`${tvResearchSignalEvents.length} research signal event · source=${tvResearchSignalEvents[0].source||"—"}`:"Research signal event bulunamadı; trade marker fallback kullanılabilir.";const lastRow=data.rows?.[data.rows.length-1];if(lastRow)updateTvLegendAtRow(lastRow);requestAnimationFrame(()=>tvUpdateResearchZones());}

async function loadTradingViewResearchChart(){const symbol=String($("tvSymbol")?.value||"").trim().toUpperCase();const interval=$("tvInterval")?.value||"1d";const limit=Number($("tvLimit")?.value||500);if(!symbol){$("tvChartStatus").textContent="Sembol girin.";return;}$("tvInfoSymbol").textContent=symbol;$("tvChartStatus").textContent="MarketHQ historical OHLCV yükleniyor…";$("tvResearchChart").innerHTML='<div class="tv-chart-empty">Tarihsel veri yükleniyor…</div>';try{const end=new Date(),start=new Date(end.getTime()-8*365*24*60*60*1000);const params=new URLSearchParams({symbol,start:start.toISOString().slice(0,10),end:end.toISOString().slice(0,10),interval,limit:String(limit)});const response=await get("/api/research-data?"+params.toString());const data=response.data||{};if(!data.available||!Array.isArray(data.rows)||!data.rows.length)throw new Error(data.error||"Tarihsel OHLCV verisi bulunamadı.");tvResearchRows=data.rows.slice();tvSelectedChartPayload=null;updateTvResearchInfo(data);createTvResearchChart(data);renderTradeDiagnostics();await loadTradingViewResearchSignals(data.resolved_symbol||data.symbol||symbol);}catch(error){destroyTvResearchChart();$("tvResearchChart").innerHTML=`<div class="tv-chart-empty">${esc(error?.message||"Chart yüklenemedi.")}</div>`;$("tvChartStatus").textContent="Chart yüklenemedi.";}}
async function loadTradingViewResearchSignals(symbol){tvResearchSignalEvents=[];try{const strategyId=String($("strategyId")?.textContent||"").trim();const qs=new URLSearchParams({symbol:String(symbol||""),limit:"250"});if(strategyId&&strategyId!=="—")qs.set("strategy_id",strategyId);const response=await get(`/api/research-signals?${qs.toString()}`);const data=response.data||{};tvResearchSignalEvents=Array.isArray(data.events)?data.events:[];$("tvInfoSignals").textContent=tvResearchSignalEvents.length?`${tvResearchSignalEvents.length} research signal event · source=${data.source||"—"}`:`Research signal event yok · source=${data.source||"—"}`;if(tvResearchCandleSeries&&tvResearchMarkers)tvResearchMarkers.setMarkers(buildTvActiveMarkers(symbol));tvUpdateResearchZones();renderRegimeAndStress();return data;}catch(error){$("tvInfoSignals").textContent=`Research signal API kullanılamadı: ${error?.message||"bilinmeyen hata"}`;return null;}}
function toggleTvSignals(button){tvResearchSignalsEnabled=!tvResearchSignalsEnabled;const symbol=$("tvSymbol")?.value||"";if(tvResearchCandleSeries&&tvResearchMarkers)tvResearchMarkers.setMarkers(buildTvActiveMarkers(symbol));if(button)button.textContent=tvResearchSignalsEnabled?"SIGNALS ON":"SIGNALS OFF";$("tvChartStatus").textContent=tvResearchSignalsEnabled?"Research signals enabled":"Research signals disabled";}
function toggleTvResearchZones(button){tvResearchZonesEnabled=!tvResearchZonesEnabled;if(button)button.textContent=tvResearchZonesEnabled?"RESEARCH ZONES ON":"RESEARCH ZONES OFF";tvUpdateResearchZones();}
function toggleTvTradePath(button){tvResearchTradePathEnabled=!tvResearchTradePathEnabled;if(button)button.textContent=tvResearchTradePathEnabled?"TRADE PATH ON":"TRADE PATH OFF";if(!tvResearchTradePathEnabled){tvClearSelectedTradePath();return;}if(tvSelectedChartPayload?.type==="TRADE")tvDrawSelectedTradePath(tvSelectedChartPayload.trade);}
function fitTradingViewResearchChart(){if(tvResearchChart)tvResearchChart.timeScale().fitContent();}
function toggleTvEma(button){tvResearchEmaEnabled=!tvResearchEmaEnabled;if(tvResearchEma20)tvResearchEma20.applyOptions({visible:tvResearchEmaEnabled});if(tvResearchEma50)tvResearchEma50.applyOptions({visible:tvResearchEmaEnabled});if(button)button.textContent=tvResearchEmaEnabled?"EMA ON":"EMA OFF";}
function useSelectedTradeInTvChart(){const selected=selectedTradeDataset()?.trades?.find(x=>Number(x.trade_id)===selectedTradeId);if(!selected){$("tvChartStatus").textContent="Önce Trade Viewer'dan bir trade seçin.";return;}$("tvSymbol").value=String(selected.symbol||"").toUpperCase();$("tvInfoTrade").textContent=`Trade #${selected.trade_id} · ${selected.side||"—"} · ${short(selected.entry_time,30)} → ${short(selected.exit_time,30)}`;tvPendingTradeSelection=selected;loadTradingViewResearchChart();focusId("tradingview");}

function renderTradingViewResearchContext(snapshot){
  const strategy = snapshot?.strategy || {};
  const pipeline = strategy.pipeline?.strategy || {};
  const decision = strategy.final_decision?.decision || {};
  const learning = strategy.learning?.ranking || {};
  const consolidation = strategy.consolidation?.summary || {};
  tvResearchScope = pipeline.scope || pipeline.validation_scope || pipeline.validationScope || strategy.scope || null;
  const strategyName = pipeline.strategy_name || pipeline.strategy_id || "—";
  const experiment = pipeline.experiment_id || pipeline.experimentId || strategy.experiment_id || strategy.experimentId || "—";
  const question = consolidation.next_research_question || learning.next_research_question || "—";
  $("tvInfoStrategy").textContent = strategyName;
  $("tvInfoExperiment").textContent = `Experiment: ${experiment}`;
  $("tvInfoDecision").textContent = decision.decision || "—";
  $("tvInfoDecisionAction").textContent = decision.action || "—";
  $("tvInfoQuestion").textContent = question;
  tvUpdateResearchZones();
}

function renderAll(x){
 const b=x.brain||{},l=x.learning||{},k=x.knowledge||{};
 $("kNodes").textContent=num(b.nodes);$("kEdges").textContent=num(b.edges);$("kEpisodes").textContent=num(b.episodes);$("kClaims").textContent=num(b.claims);$("kEvents").textContent=num(b.learning_events);$("kQueue").textContent=num(b.research_queue_active);$("kKnowledge").textContent=num(k.items);$("kRules").textContent=num(l.learned_rules);
 $("safety").textContent=x.safety?.execution_enabled===false?"RESEARCH ONLY":"CHECK SAFETY";$("safety").className="pill "+(x.safety?.execution_enabled===false?"safe":"bad");
 $("schema").textContent=x.schema?.status==="READY"?"SCHEMA READY":"SCHEMA DEGRADED";$("schema").className="pill "+(x.schema?.status==="READY"?"safe":"bad");
 renderStrategy(x.strategy||{});renderDecisionCockpit(x.strategy||{});renderValidationBoard(x.strategy||{});renderEvidence(x.strategy||{});renderTradingViewResearchContext(x);renderRegimeAndStress();renderSymbols(x.symbol_explorer||{});renderCharts(x.symbol_explorer||{});renderBrain(b);renderLearning(l);renderDB(x.database||{});$("errorBox").style.display="none";
}
async function loadAll(){
 try{const d=await get("/api/snapshot");renderAll(d.data)}
 catch(e){$("schema").textContent="BACKEND ERROR";$("schema").className="pill bad";$("errorBox").style.display="block";$("errorBox").textContent="Backend bağlantı hatası: "+e.message;console.error(e)}
}
loadAll();loadTrades();setTimeout(loadTradingViewResearchChart,250);setInterval(loadAll,5000);
</script>
</body>
</html>
"""

class DashboardUIHandler(BaseHTTPRequestHandler):
    def send_bytes(self, payload, content_type, status=200):
        body = payload if isinstance(payload, bytes) else payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def proxy_backend(self, path):
        try:
            with urllib.request.urlopen(BACKEND_BASE + path, timeout=15) as response:
                body = response.read()
                content_type = response.headers.get("Content-Type","application/json; charset=utf-8")
                self.send_bytes(body, content_type, response.status)
        except urllib.error.HTTPError as exc:
            body = exc.read() or json.dumps(
                {"success":False,"error":"Backend HTTP error "+str(exc.code)},
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_bytes(body, "application/json; charset=utf-8", exc.code)
        except Exception as exc:
            body=json.dumps(
                {"success":False,"error":"UI proxy backend bağlantı hatası: "+str(exc),"backend":BACKEND_BASE},
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_bytes(body, "application/json; charset=utf-8", 502)

    def do_GET(self):
        path=self.path.split("?",1)[0]
        if path in ("/","/index.html"):
            self.send_bytes(HTML,"text/html; charset=utf-8")
            return
        if path.startswith("/api/"):
            # Keep the query parameters (symbol, entry_time, exit_time, etc.)
            # when proxying requests to the backend.
            self.proxy_backend(self.path)
            return
        if path=="/health":
            self.send_bytes(json.dumps({
                "status":"ok",
                "ui_version":"DASHBOARD_UI_V6.2_TRADINGVIEW_V5",
                "backend":BACKEND_BASE,
                "connection_mode":"SAME_ORIGIN_PROXY",
                "research_only":True,
                "execution_enabled":False,
            },ensure_ascii=False),"application/json; charset=utf-8")
            return
        self.send_bytes(json.dumps({"error":"Not found"},ensure_ascii=False),"application/json; charset=utf-8",404)

    def log_message(self, format_string, *args):
        return

def main():
    print()
    print("="*76)
    print("MARKETHQ DASHBOARD UI V6.2 · TradingView V5")
    print("="*76)
    print(f"UI Server          : {HOST}:{PORT}")
    print(f"Backend            : {BACKEND_BASE}")
    print("Connection Mode    : SAME-ORIGIN PROXY")
    print("Strategy Explorer  : ENABLED")
    print("Performance Charts : ENABLED")
    print("Trade Viewer V3.1  : ENABLED")
    print("Research Only      : True")
    print("Execution Enabled  : False")
    print("Refresh            : 5 seconds")
    print()
    print("CTRL+C ile durdur.")
    print()
    server=ThreadingHTTPServer((HOST,PORT),DashboardUIHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nUI kapatıldı.")
    finally:
        server.server_close()

if __name__=="__main__":
    main()



