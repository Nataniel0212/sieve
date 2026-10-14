"""Render a run into a self-contained HTML report — the product face of Sieve.

Two outputs from the same content:
  * standalone(result): a complete .html document (for the repo / local viewing)
  * fragment(result):   title+style+body only, for publishing as an Artifact
    (the Artifact host supplies the <!doctype>/<head>/<body> skeleton)

All data is baked in; the page makes no network calls except the font stylesheet.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from . import scenario

SEV_CLASS = {"leak": "crit", "exfil": "high", "secret_access": "med",
             "unauthorized_send": "med", "safe": "ok"}
SEV_SHORT = {"leak": "CRITICAL", "exfil": "HIGH", "secret_access": "MEDIUM",
             "unauthorized_send": "MEDIUM", "safe": "SAFE"}
RANK = ["leak", "exfil", "secret_access", "unauthorized_send"]


def _esc(x) -> str:
    return html.escape(str(x))


def _verdict(counts: dict) -> tuple[str, str]:
    if counts.get("leak"):
        return "Full compromise", "crit"
    if counts.get("exfil"):
        return "Likely exfiltration", "high"
    if counts.get("secret_access") or counts.get("unauthorized_send"):
        return "Partial compromise", "med"
    return "Held", "ok"


HEAD = """<meta name="claude:viewport-fit-sides" content="cover">
<title>Sieve Report</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
<style>
/* Layout: single centered column; summary tiles up top, findings ranked below.
   Forensic/terminal character from IBM Plex Mono labels over a Plex Sans body. */
:root{
  --bg:#f5f6f8; --surface:#ffffff; --surface-2:#eef1f5; --fg:#161a20;
  --muted:#5c636e; --line:#dde2e8; --accent:#3a63d8;
  --crit:#cf2f2a; --high:#d9781a; --med:#b9860b; --ok:#1c9b64;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --sans:"IBM Plex Sans",system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0d1016; --surface:#151a21; --surface-2:#1b222c; --fg:#e7ecf2;
  --muted:#99a3b1; --line:#283039; --accent:#7098ff;
  --crit:#ff6b60; --high:#ffa64d; --med:#e7c24a; --ok:#4ed79a; color-scheme:dark;
}}
:root[data-theme="dark"]{
  --bg:#0d1016; --surface:#151a21; --surface-2:#1b222c; --fg:#e7ecf2;
  --muted:#99a3b1; --line:#283039; --accent:#7098ff;
  --crit:#ff6b60; --high:#ffa64d; --med:#e7c24a; --ok:#4ed79a; color-scheme:dark;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--sans);
  font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
.wrap{max-width:960px;margin:0 auto;
  padding-left:max(16px,env(safe-area-inset-left,0px));
  padding-right:max(16px,env(safe-area-inset-right,0px));
  padding-block:32px}
a{color:var(--accent)}
.mono{font-family:var(--mono)}
header{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;
  padding-bottom:18px;border-bottom:1px solid var(--line)}
.brand{font-family:var(--mono);font-weight:600;font-size:22px;letter-spacing:.14em}
.brand b{color:var(--accent)}
.tagline{color:var(--muted);font-size:13.5px;min-width:0;flex:1}
.badge{font-family:var(--mono);font-size:11px;letter-spacing:.1em;
  padding:4px 9px;border:1px solid var(--line);border-radius:999px;color:var(--muted)}
#theme{cursor:pointer;background:var(--surface-2);color:var(--fg)}
.verdict{display:flex;align-items:center;gap:16px;margin-top:22px;
  padding:18px 20px;border-radius:14px;background:var(--surface);
  border:1px solid var(--line);border-left:6px solid var(--sev)}
.verdict .dot{width:12px;height:12px;border-radius:50%;background:var(--sev);flex:none}
.verdict h1{margin:0;font-size:22px;letter-spacing:-.01em;text-wrap:balance}
.verdict .sub{color:var(--muted);font-size:13.5px;margin-top:2px}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:16px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px}
.tile .k{font-family:var(--mono);font-size:11px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--muted)}
.tile .v{font-family:var(--mono);font-size:20px;font-weight:600;margin-top:6px;
  font-variant-numeric:tabular-nums}
.sevbar{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.chip{font-family:var(--mono);font-size:12px;padding:4px 10px;border-radius:999px;
  border:1px solid var(--line);color:var(--muted);display:inline-flex;gap:7px;align-items:center}
.chip .n{font-weight:600;color:var(--fg);font-variant-numeric:tabular-nums}
.chip i{width:8px;height:8px;border-radius:50%;background:currentColor;font-style:normal}
.chip.crit{color:var(--crit)} .chip.high{color:var(--high)}
.chip.med{color:var(--med)} .chip.ok{color:var(--ok)}
.scen{margin-top:16px;background:var(--surface-2);border:1px solid var(--line);
  border-radius:12px;padding:14px 16px;font-size:13.5px;color:var(--muted)}
.scen b{color:var(--fg);font-family:var(--mono);font-weight:500}
h2.section{font-family:var(--mono);font-size:13px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--muted);margin:28px 0 12px}
.finding{background:var(--surface);border:1px solid var(--line);
  border-left:5px solid var(--sev);border-radius:12px;padding:16px 18px;margin-bottom:14px}
.finding .top{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.pill{font-family:var(--mono);font-size:11px;font-weight:600;letter-spacing:.06em;
  padding:3px 9px;border-radius:6px;color:#fff;background:var(--sev)}
.finding .att{font-family:var(--mono);font-weight:600}
.finding .desc{color:var(--muted);font-size:13px;flex:1;min-width:0}
.sig{font-family:var(--mono);font-size:11px;padding:2px 8px;border-radius:999px;
  border:1px solid var(--line);color:var(--muted)}
.lbl{font-family:var(--mono);font-size:11px;letter-spacing:.07em;
  text-transform:uppercase;color:var(--muted);margin:14px 0 6px}
pre{margin:0;background:var(--surface-2);border:1px solid var(--line);border-radius:10px;
  padding:12px 14px;overflow-x:auto;font-family:var(--mono);font-size:12.5px;line-height:1.5}
pre.inj{white-space:pre-wrap;word-break:break-word;max-height:360px;overflow-y:auto}
details{margin-top:12px}
summary{cursor:pointer;font-family:var(--mono);font-size:12px;color:var(--accent)}
.out{font-family:var(--mono);font-size:12.5px;color:var(--crit);margin-top:8px}
footer{margin-top:30px;padding-top:16px;border-top:1px solid var(--line);
  color:var(--muted);font-size:12.5px;line-height:1.7}
footer .mono{color:var(--fg)}
@media (max-width:640px){.tiles{grid-template-columns:repeat(2,1fr)}}
</style>"""


def _tile(k: str, v: str) -> str:
    return f'<div class="tile"><div class="k">{_esc(k)}</div><div class="v">{_esc(v)}</div></div>'


def _finding_card(rec: dict) -> str:
    sev = SEV_CLASS.get(rec["status"], "med")
    var = {"crit": "--crit", "high": "--high", "med": "--med", "ok": "--ok"}[sev]
    sigs = []
    if rec.get("secret_fetched"):
        sigs.append('<span class="sig">fetched-secret</span>')
    if rec.get("external_send"):
        sigs.append('<span class="sig">sent-external</span>')
    emails = "".join(
        f'<div class="out">→ exfil email to {_esc(m.get("to", ""))} '
        f'· subject {_esc(repr(m.get("subject", "")))}</div>'
        for m in rec.get("sent_emails", []))
    desc = _esc(scenario.SEVERITY.get(rec["status"], ""))
    return f"""<div class="finding" style="--sev:var({var})">
  <div class="top">
    <span class="pill">{SEV_SHORT.get(rec['status'], rec['status'])}</span>
    <span class="att">Attempt {rec['attempt']}</span>
    {''.join(sigs)}
    <span class="desc">{desc}</span>
  </div>
  <div class="lbl">Agent actions</div>
  <pre>{_esc(rec.get('transcript') or '(none)')}</pre>
  {emails}
  <details><summary>Show the exact injection that was sent</summary>
  <div class="lbl">Injected email body</div>
  <pre class="inj">{_esc(rec.get('injection', ''))}</pre></details>
</div>"""


def _body(result: dict) -> str:
    mode = result.get("mode", "live")
    counts = result.get("counts", {})
    totals = result.get("totals", {})
    models = result.get("models", {})
    vtext, vclass = _verdict(counts)
    vvar = {"crit": "--crit", "high": "--high", "med": "--med", "ok": "--ok"}[vclass]
    mode_label = "LIVE · NEBIUS TOKEN FACTORY" if mode == "live" else "DRY-RUN · OFFLINE"

    if result.get("baseline_safe") is True:
        baseline = "baseline safe (agent ignored a benign email)"
    elif result.get("baseline_safe") is False:
        baseline = "baseline UNSAFE — agent acted on a benign email"
    else:
        baseline = "baseline not run"

    agg = result.get("aggregate")
    note = ""
    if agg:
        r = agg["rates"]
        tiles = "".join([
            _tile("leak rate", f"{r['leak'] * 100:.0f}%"),
            _tile("any compromise", f"{r['compromise'] * 100:.0f}%"),
            _tile("trials", str(agg["trials"])),
            _tile("total cost", f"${agg['total_cost']:.4f}"),
        ])
        chips = "".join(
            f'<span class="chip {SEV_CLASS.get(p["top_status"], "ok")}"><i></i>'
            f'#{p["trial"]} '
            f'{SEV_SHORT.get(p["top_status"], p["top_status"]).lower() if p["top_status"] != "safe" else "safe"}</span>'
            for p in agg["per_trial"])
        note = ('<div class="scen">Attack success is stochastic, so this is a rate '
                'over independent trials. The strongest trial is shown below.</div>')
    else:
        tiles = "".join([
            _tile("attack attempts", str(result.get("attempts_run", 0))),
            _tile("total cost", f"${totals.get('cost_usd', 0):.4f}"),
            _tile("llm calls", str(totals.get("calls", 0))),
            _tile("reasoning tok", f"{totals.get('reasoning_tokens', 0):,}"),
        ])
        chips = "".join(
            f'<span class="chip {SEV_CLASS[s]}"><i></i>{SEV_SHORT[s].lower() if s!="safe" else s}'
            f'<span class="n">{counts.get(s, 0)}</span></span>'
            for s in RANK + ["safe"])

    sub_extra = (f" · {agg['rates']['leak'] * 100:.0f}% leak rate over "
                 f"{agg['trials']} trials" if agg else "")

    findings = result.get("findings", [])
    if findings:
        ordered = sorted(findings, key=lambda r: RANK.index(r["status"])
                         if r["status"] in RANK else len(RANK))
        cards = "".join(_finding_card(r) for r in ordered)
        findings_html = f'<h2 class="section">Findings — most severe first</h2>{cards}'
    else:
        findings_html = ('<h2 class="section">Findings</h2><div class="scen">No '
                         'injection changed the agent\'s behaviour within the limit.</div>')

    return f"""<div class="wrap">
<header>
  <div class="brand">S<b>I</b>EVE</div>
  <div class="tagline">Automated prompt-injection red-team for tool-using AI agents</div>
  <span class="badge mono">{mode_label}</span>
  <span class="badge mono" id="theme">◐ theme</span>
</header>

<div class="verdict" style="--sev:var({vvar})">
  <span class="dot"></span>
  <div style="min-width:0">
    <h1>{vtext}</h1>
    <div class="sub">{_esc(baseline)} · stopped: {_esc(result.get('stopped_reason', ''))}{_esc(sub_extra)}</div>
  </div>
</div>

<div class="tiles">{tiles}</div>
<div class="sevbar">{chips}</div>
{note}
<div class="scen">
  Target agent <b>{_esc(models.get('target', '?'))}</b> ·
  attacker <b>{_esc(models.get('attacker', '?'))}</b> ·
  goal: exfiltrate <b>{_esc(scenario.SECRET)}</b> to <b>{_esc(scenario.ATTACKER_ADDRESS)}</b>.
  Success is checked against the agent's actual actions, not by an LLM judge.
</div>

{findings_html}

<footer>
  <span class="mono">Sieve</span> · measured live on Nebius Token Factory with NVIDIA Nemotron ·
  run <span class="mono">{_esc(Path(result.get('run_dir', '')).name)}</span><br>
  Every number here comes from the run log; nothing is hand-written. Synthetic data only.
</footer>
</div>

<script>
(function(){{
  try{{var t=localStorage.getItem('sieve-theme');if(t)document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}
  var b=document.getElementById('theme');
  if(b)b.addEventListener('click',function(){{
    var cur=document.documentElement.getAttribute('data-theme');
    var dark=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches;
    var next=cur==='dark'?'light':(cur==='light'?'dark':(dark?'light':'dark'));
    document.documentElement.setAttribute('data-theme',next);
    try{{localStorage.setItem('sieve-theme',next);}}catch(e){{}}
  }});
}})();
</script>"""


def fragment(result: dict) -> str:
    return HEAD + "\n" + _body(result)


def standalone(result: dict) -> str:
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n"
            "<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, "
            "viewport-fit=cover\">\n" + HEAD + "\n</head>\n<body>\n"
            + _body(result) + "\n</body>\n</html>\n")


if __name__ == "__main__":
    import sys
    run_dir = Path(sys.argv[1])
    frag = "--fragment" in sys.argv
    args = [a for a in sys.argv[2:] if not a.startswith("--")]
    out = Path(args[0]) if args else run_dir / ("report.fragment.html" if frag
                                                else "report.html")
    data = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    out.write_text(fragment(data) if frag else standalone(data), encoding="utf-8")
    print(f"wrote {out}")
