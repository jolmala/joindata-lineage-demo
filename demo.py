"""Run both demos on synthetic data and write an HTML report.

    python demo.py            # writes out/report.html and out/summary.json

Part 1 traces every cell of a regulatory report back through Azure SQL, Unity Catalog, ADLS and
Data Factory to its source systems, then reconciles reported figures against the warehouse.
Part 2 reads a PowerCenter repository export and shows mappings, lineage and unscheduled objects.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

from lineage import graph as lg
from lineage import sample
from powercenter import parser as pc

ROOT = Path(__file__).parent


def lineage_part(work: Path) -> dict:
    sample.write(work)
    edges = (lg.parse_adf(work / "adf_pipelines.json") + lg.parse_uc_lineage(work / "uc_table_lineage.csv")
             + lg.parse_sql_views(work / "azure_sql_views.sql", "sql:azure/s2rpt."))
    mapping = lg.parse_mapping(work / "report_mapping.csv", "sql:azure/")
    edges += [dict(src=m["view"], dst=m["cell"], via=f"mapping: {m['column']}", source="Reporting", when="") for m in mapping]
    col_edges = (lg.parse_uc_column_lineage(work / "uc_column_lineage.csv")
                 + lg.parse_sql_view_columns(work / "azure_sql_views.sql", "sql:azure/s2rpt."))
    g = lg.Graph(edges, sample.SOURCES, col_edges)

    cells = []
    for m in mapping:
        nodes, used, breaks = g.trace(f"{m['view']}#{m['column']}")
        stale = sorted({e["when"][:10] for e in used if e["when"] and e["when"][:10] < sample.REPORT_DATE})
        rep, dw = sample.REPORTED[m["row"]], sample.WAREHOUSE[m["row"]]
        cells.append(dict(
            cell=f"{m['table']} {m['row']}", column=m["column"],
            sources=sorted(n for n in nodes if n in sample.SOURCES),
            storages=sorted({lg.storage_of(n) for n in nodes} - {"Report"}, key=lambda s: lg.TIER.get(s, 9)),
            breaks=sorted(set(breaks)), stale=stale, reported=rep, warehouse=dw,
            status="OK" if abs(rep - dw) < 0.05 else "DIFFERENCE"))
    return dict(edges=edges, cells=cells)


def powercenter_part() -> dict:
    maps, flows = pc.read_export(ROOT / "samples" / "powercenter" / "REP_DEMO_export.xml")
    edges = pc.lineage_edges(maps)
    report_target = "REG_LCR"
    return dict(
        mappings=[dict(name=m.name, sources=m.sources, targets=m.targets, steps=m.logic_steps, size=m.size) for m in maps],
        workflows=[dict(name=w.name, sessions=len(w.sessions)) for w in flows],
        upstream={report_target: pc.upstream(edges, report_target)},
        unscheduled=pc.unscheduled(maps, flows))


# --------------------------------------------------------------------------- HTML
LAYERS = ["Sources", "ADLS Gen2", "Bronze", "Silver", "Gold", "Azure SQL", "View", "Report"]
ABBR = {"SQL Server (on-prem)": "On-prem SQL", "SFTP": "SFTP", "ADLS Gen2": "ADLS",
        "Unity Catalog (Delta)": "Unity Catalog", "Azure SQL Database": "Azure SQL"}


def layer(n: str) -> int:
    st = lg.storage_of(n)
    if st in ("SQL Server (on-prem)", "SFTP"):
        return 0
    if st == "ADLS Gen2":
        return 1
    if st == "Unity Catalog (Delta)":
        return {"bronze": 2, "silver": 3, "gold": 4}.get(n.split(".")[1], 4)
    if st == "Azure SQL Database":
        return 6 if ".v_" in n else 5
    return 7


def label(n: str) -> str:
    if n.startswith("report:"):
        return n.split("/", 1)[1].replace("/", " ")
    if "://" in n:
        return n.rstrip("/").split("/")[-1]
    if n.startswith("sql:"):
        return n.split("/", 1)[1].split(".", 1)[-1]
    return n.split(".", 1)[1]


def path_text(storages: list[str]) -> str:
    first = [ABBR.get(x, x) for x in storages if lg.TIER.get(x) == 0]
    rest = [ABBR.get(x, x) for x in storages if lg.TIER.get(x) != 0]
    return " → ".join(([" + ".join(first)] if first else []) + rest)


def svg_chain(edges: list[dict]) -> str:
    """Nodes in columns by layer, edges as curves from right edge to left edge."""
    nodes = sorted({e["src"] for e in edges} | {e["dst"] for e in edges}, key=lambda n: (layer(n), n))
    cols: dict[int, list[str]] = {}
    for n in nodes:
        cols.setdefault(layer(n), []).append(n)
    W, colw, boxw, rowh, top = 1180, 147, 134, 32, 34
    pos = {}
    for c, ns in cols.items():
        off = (max(len(v) for v in cols.values()) - len(ns)) * rowh / 2
        for i, n in enumerate(ns):
            pos[n] = (6 + c * colw, top + off + i * rowh)
    H = top + max(len(v) for v in cols.values()) * rowh + 6
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Lineage from source systems to report cells">']
    for c, name in enumerate(LAYERS):
        out.append(f'<text x="{6 + c * colw}" y="18" class="hd">{name}</text>')
    for e in edges:
        (x1, y1), (x2, y2) = pos[e["src"]], pos[e["dst"]]
        x1 += boxw
        mx = (x1 + x2) / 2
        out.append(f'<path d="M{x1},{y1 + 11} C{mx},{y1 + 11} {mx},{y2 + 11} {x2},{y2 + 11}" class="edge"/>')
    for n, (x, y) in pos.items():
        cls = "src" if n in sample.SOURCES else "brk" if "/manual/" in n else "node"
        out.append(f'<rect x="{x}" y="{y}" width="{boxw}" height="22" rx="5" class="{cls}"><title>{html.escape(n)}</title></rect>'
                   f'<text x="{x + 6}" y="{y + 15}" class="lb">{html.escape(label(n)[:22])}</text>')
    out.append("</svg>")
    return "".join(out)


def write_html(path: Path, lin: dict, pcd: dict, summary: dict) -> None:
    e = html.escape
    rows = "".join(
        f"<tr><td title=\"{e(c['column'])}\">{e(c['cell'])}</td><td>{e(', '.join(x.rstrip('/').split('/')[-1].replace('.dbo.', '.') for x in c['sources']))}</td>"
        f"<td class=nw>{e(path_text(c['storages']))}</td>"
        f"<td>{'<span class=bad>' + e(', '.join(b.split('/')[-1] for b in c['breaks'])) + '</span>' if c['breaks'] else ''}"
        f"{'<span class=warn>source loaded ' + e(c['stale'][0]) + '</span>' if c['stale'] else ''}</td>"
        f"<td class=n>{c['reported']:.1f}</td><td class=n>{c['warehouse']:.1f}</td>"
        f"<td><span class={'ok' if c['status'] == 'OK' else 'bad'}>{c['status']}</span></td></tr>" for c in lin["cells"])
    mrows = "".join(
        f"<tr><td><code>{e(m['name'])}</code></td><td>{e(', '.join(m['sources']))}</td><td>{e(', '.join(m['targets']))}</td>"
        f"<td class=n>{m['steps']}</td><td>{m['size']}</td><td>{'not scheduled' if m['name'] in pcd['unscheduled'] else ''}</td></tr>"
        for m in pcd["mappings"])
    tiles = "".join(f'<div class="tile"><b>{v}</b><span>{k}</span></div>' for k, v in (
        ("report cells traced to source", f"{summary['cells_traced']} / {summary['cells']}"),
        ("lineage break", len(summary["breaks"])),
        ("reconciliation differences", summary["differences"]),
        ("PowerCenter mappings not scheduled", len(pcd["unscheduled"]))))
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Regulatory lineage demo</title><style>
:root{{--bg:#f7f7f5;--card:#fff;--ink:#1d2327;--mut:#5b6670;--line:#e3e5e8;--acc:#1f5fa8;--ok:#2e7d4f;--bad:#b3261e;--warn:#9a6700}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16191c;--card:#1f2327;--ink:#e8eaed;--mut:#9aa4ad;--line:#33393f;--acc:#7fb0ea;--ok:#6cc596;--bad:#f08a82;--warn:#e0b44c}}}}
body{{margin:0;font:15px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--ink)}}main{{max-width:1220px;margin:0 auto;padding:28px 20px 60px}}
h1{{font-size:26px;margin:0 0 6px}}h2{{font-size:19px;margin:34px 0 8px}}.mut{{color:var(--mut)}}
.tiles{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}}.tile{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}}.tile b{{display:block;font-size:24px}}.tile span{{color:var(--mut);font-size:13px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;overflow-x:auto}}
table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top}}th{{color:var(--mut);font-size:12px;text-transform:uppercase}}td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.ok{{color:var(--ok);font-weight:600}}.bad{{color:var(--bad);font-weight:600}}.warn{{color:var(--warn);font-weight:600;display:block}}
svg{{width:100%;height:auto}}.edge{{fill:none;stroke:var(--mut);stroke-opacity:.45}}.node{{fill:var(--card);stroke:var(--line)}}.src{{fill:var(--card);stroke:var(--acc);stroke-width:2}}.brk{{fill:var(--card);stroke:var(--bad);stroke-width:2}}
.lb{{fill:var(--ink);font-size:11px}}td.nw{{white-space:nowrap;font-size:12.5px}}td{{font-size:13.5px}}.hd{{fill:var(--mut);font-size:12px;font-weight:600;text-transform:uppercase}}
@media(max-width:800px){{.tiles{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><main>
<h1>Regulatory lineage demo</h1>
<p class="mut">All data is synthetic. Part 1: an own-funds report traced through Azure. Part 2: a PowerCenter repository export.</p>
<div class="tiles">{tiles}</div>
<h2>1. Report cell → source system</h2>
<div class="card">{svg_chain(lin['edges'])}<p class="mut">Blue = declared source system. Red = break: data that enters the lake with no pipeline behind it.</p></div>
<div class="card" style="margin-top:12px"><table><thead><tr><th>Report cell</th><th>Source systems</th><th>Storage path</th><th>Findings</th><th class=n>Reported, M€</th><th class=n>Warehouse, M€</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table>
<p class="mut">The SCR difference is explained by the lineage: the actuarial file was loaded on 29 December, two days before the reporting date.</p></div>
<h2>2. PowerCenter export</h2>
<div class="card"><table><thead><tr><th>Mapping</th><th>Sources</th><th>Targets</th><th class=n>Logic steps</th><th>Size</th><th></th></tr></thead><tbody>{mrows}</tbody></table>
<p class="mut">Tables upstream of <code>REG_LCR</code>: {e(', '.join(sorted(pcd['upstream']['REG_LCR'])))}</p></div>
</main></body></html>"""
    path.write_text(page, encoding="utf-8")


def main(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    lin = lineage_part(out / "extracts")
    pcd = powercenter_part()
    summary = dict(
        cells=len(lin["cells"]), cells_traced=sum(bool(c["sources"]) for c in lin["cells"]),
        breaks=sorted({b for c in lin["cells"] for b in c["breaks"]}),
        stale_cells=[c["cell"] for c in lin["cells"] if c["stale"]],
        differences=sum(c["status"] != "OK" for c in lin["cells"]),
        mappings=len(pcd["mappings"]), unscheduled=pcd["unscheduled"])
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_html(out / "report.html", lin, pcd, summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "out")), indent=2))
