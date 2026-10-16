"""Render the measured results into public/index.html as static HTML.

    py -3.12 scripts/build_page.py

Reads only results/*.json and results/*.md (written by the benchmark and the
model comparison) and fills the <!-- build:NAME --> ... <!-- /build:NAME -->
blocks, so no number on the page is typed by hand and the results need no
JavaScript. Re-run after a new benchmark.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sieve.benchmark import wilson  # noqa: E402
from sieve.scenarios import REGISTRY  # noqa: E402

RES = ROOT / "results"
PAGE = ROOT / "public" / "index.html"
LABEL = {"inbox": "Email assistant", "bank": "Banking assistant", "docs": "Document assistant"}
NAMES = {"nvidia/Nemotron-3_5-Lightning": "Nemotron 3.5 Lightning",
         "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B": "Nemotron 3 Nano 30B",
         "nvidia/Nemotron-3-Ultra-550b-a55b": "Nemotron 3 Ultra"}


def pct(p: float) -> str:
    return f"{round(p * 100)}%"


def parse_md(path: Path) -> dict:
    """The 15 Oct run only survives as its markdown report; read its rates back."""
    text = path.read_text(encoding="utf-8")
    run = {"total_cost": float(re.search(r"total cost \$([\d.]+)", text).group(1)),
           "trials_per": int(re.search(r"Trials per scenario: (\d+)", text).group(1)),
           "scenarios": []}
    for key, body in re.findall(r"^## .*?\((\w+)\).*?\n(.*?)(?=^## |\Z)", text, re.M | re.S):
        k, n = map(int, re.search(r"P\(critical\).*?\((\d+)/(\d+)\)", body).groups())
        p, lo, hi = wilson(k, n)
        mean = float(re.search(r"mean ([\d.]+)", body).group(1))
        refused = float(re.search(r"Attacker refused ([\d.]+)%", body).group(1)) / 100
        run["scenarios"].append({"key": key, "exceedance": {"critical": {
            "k": k, "n": n, "p": p, "lo": lo, "hi": hi}}, "attempts": {"mean": mean},
            "attacker_refusal_rate": refused})
    return run


def ci_row(label: str, e: dict, note: str) -> str:
    low = " low" if e["p"] < 0.5 else ""
    return (
        f'<div class="cirow"><div class="lbl"><span style="color:var(--fg)">{escape(label)}</span>'
        f'<b>{pct(e["p"])}</b></div>'
        f'<div class="track" role="img" aria-label="{escape(label)}: {pct(e["p"])}, 95% CI '
        f'{pct(e["lo"])} to {pct(e["hi"])}">'
        f'<div class="fill{low}" style="width:{e["p"] * 100:.1f}%"></div>'
        f'<div class="whisk" style="left:{e["lo"] * 100:.1f}%;width:{(e["hi"] - e["lo"]) * 100:.1f}%"></div>'
        f'</div><div class="lbl"><span>{escape(note)}</span>'
        f'<span>95% CI {pct(e["lo"])}–{pct(e["hi"])}</span></div></div>')


def bench_card(title: str, run: dict) -> str:
    rows = "".join(
        ci_row(LABEL[s["key"]], s["exceedance"]["critical"],
               f'{s["exceedance"]["critical"]["k"]}/{s["exceedance"]["critical"]["n"]} · '
               f'mean {s["attempts"]["mean"]} attempts')
        for s in run["scenarios"])
    refusals = " / ".join(pct(s.get("attacker_refusal_rate", 0)) for s in run["scenarios"])
    return (f'<div class="card"><div class="cap">{escape(title)} · {run["trials_per"]} trials per agent · '
            f'${run["total_cost"]:.2f}</div><div class="cibar">{rows}</div>'
            f'<div class="note">Attacker refusals: {refusals}.</div></div>')


def render() -> tuple[str, dict]:
    day1 = parse_md(RES / "benchmark-2026-10-15.md")
    day2 = json.loads((RES / "benchmark-2026-10-16.json").read_text(encoding="utf-8"))
    comp = json.loads((RES / "compare-2026-10-15.json").read_text(encoding="utf-8"))
    stats = json.loads((RES / "campaign-stats-2026-10-16.json").read_text(encoding="utf-8"))
    target = NAMES.get(day2["models"]["target"], day2["models"]["target"])
    by_key = {s["key"]: s for s in day2["scenarios"]}
    hero = '<figcaption class="cap">Full compromise · Lightning agents · 16 Oct 2026</figcaption>'
    hero += '<div class="cibar">' + "".join(
        ci_row(LABEL[key], by_key[key]["exceedance"]["critical"],
               f'{by_key[key]["exceedance"]["critical"]["k"]}/{by_key[key]["exceedance"]["critical"]["n"]} campaigns')
        for key in ("bank", "inbox", "docs")) + '</div>'
    hero += '<div class="foot-note">Whiskers: 95% Wilson intervals. Synthetic agents; not a general model rating.</div>'
    measured = stats[day2["models"]["target"]]
    total = day1["trials_per"] * len(day1["scenarios"]) + day2["total_trials"]
    facts = "".join(f'<div class="fact"><div class="v">{value}</div><div class="k">{label}</div></div>'
                    for value, label in [
                        (str(total), "benchmark campaigns · two days"),
                        (f'${day2["total_cost"]:.2f}', f'{day2["total_trials"]}-campaign replication'),
                        (f'${measured["median_cost_usd"]:.4f}', "median campaign · replication"),
                        (f'{measured["median_model_time_s"]:.1f}s', "median model time · replication")])
    bench = '<div class="bench">' + bench_card("15 Oct · first run", day1)
    bench += bench_card("16 Oct · independent replication", day2) + '</div>'
    bench += (f'<p class="note">Target: {escape(target)}. Up to 10 attempts per campaign. '
              'Each interval describes one day, not pooled trials. '
              '<a href="https://github.com/Nataniel0212/sieve/tree/main/results">Raw reports and methodology ↗</a></p>')
    compare = '<div class="tablewrap"><table class="comparison"><caption>Full-compromise rate by target model</caption><thead><tr><th>Target model</th>'
    compare += "".join(f'<th>{escape(LABEL[k])}</th>' for k in comp["scenarios"]) + '</tr></thead><tbody>'
    for model in comp["models"]:
        compare += f'<tr><th scope="row">{escape(model["name"])}</th>'
        for key in comp["scenarios"]:
            e = model["scenarios"][key]["critical"]
            cls = "hot" if e["p"] >= 0.5 else "cool" if e["k"] == 0 else ""
            compare += (f'<td class="cell {cls}"><div class="p">{pct(e["p"])}</div>'
                        f'<div class="kn">{e["k"]}/{e["n"]} · CI {pct(e["lo"])}–{pct(e["hi"])}</div></td>')
        compare += '</tr>'
    compare += (f'</tbody></table></div><p class="note">{comp["trials_per"]} campaigns per cell · '
                f'${comp["total_cost"]:.2f} total. Zero observed compromises does not establish immunity. '
                'The email intervals for Lightning and Nano overlap.</p>')
    tech = '<div class="techs">'
    for scn in day2["scenarios"]:
        tech += f'<div class="card"><div class="cap">{escape(LABEL[scn["key"]])}</div>'
        for t in scn["techniques"]:
            tech += (f'<div class="trow"><span class="nm">{escape(t["name"])}</span>'
                     f'<span class="bar" aria-hidden="true"><i style="width:{t["rate"] * 100:.1f}%"></i></span>'
                     f'<span class="v"><b>{pct(t["rate"])}</b> {t["k"]}/{t["n"]}</span></div>')
        tech += '</div>'
    tech += ('</div><p class="note">16 Oct replication. Technique order is fixed: these rates also reflect '
             'attempt position and prior feedback, not isolated causal effects.</p>')
    html = PAGE.read_text(encoding="utf-8")
    for name, body in {"hero": hero, "facts": facts, "bench": bench, "compare": compare, "tech": tech}.items():
        pattern = rf"(<!-- build:{name} -->).*?(<!-- /build:{name} -->)"
        html, count = re.subn(pattern, lambda m: m[1] + "\n" + body + "\n" + m[2], html, flags=re.S)
        if count != 1:
            raise ValueError(f"Expected exactly one build block: {name}, found {count}")
    catalog = {
        "scenarios": [{**s.meta(), "system_prompt": s.system_prompt, "user_task": s.user_task,
                       "tools": [t["function"]["name"] for t in s.tools],
                       "descriptions": s.descriptions} for s in REGISTRY.values()],
        "targets": {key: {"label": NAMES[model], "id": model} for key, model in
                    zip(("lightning", "nano", "ultra"), NAMES)},
        "replays": sorted(p.stem for p in (ROOT / "public/data/replays").glob("*.json")),
    }
    return html, catalog


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="Fail if generated assets are stale")
    args = ap.parse_args()
    html, catalog = render()
    outputs = {PAGE: html, ROOT / "public/data/catalog.json": json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"}
    for path, content in outputs.items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise SystemExit(f"Stale generated asset: {path.relative_to(ROOT)}; run scripts/build_page.py")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    print("Page and offline catalog are up to date." if args.check else "Built page and offline catalog.")


if __name__ == "__main__":
    main()
