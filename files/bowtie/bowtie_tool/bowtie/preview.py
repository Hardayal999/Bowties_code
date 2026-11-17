"""
preview.py
Draws the bowties as a web page (bowties.html) so they can be checked before
anything is sent to Riskrunner. This step is optional: Riskrunner draws its own
bowties once the data is loaded.
"""

import html
from collections import Counter
from pathlib import Path

PAGE_STYLE = """
body{font-family:Segoe UI,Arial,sans-serif;color:#222;margin:24px;font-size:13px;line-height:1.4}
h1{font-size:22px;font-weight:600}
h2{font-size:16px;font-weight:600;margin:40px 0 4px;border-top:1px solid #ccc;padding-top:16px}
table{border-collapse:collapse;margin:12px 0}
td,th{border:1px solid #ccc;padding:4px 8px;text-align:left}
td:first-child{white-space:nowrap}
th{background:#f2f2f2}
.sub{color:#666}
.bt{display:grid;grid-template-columns:1fr 150px 1fr;gap:10px;align-items:center;margin-top:12px}
.col{display:flex;flex-direction:column;gap:10px}
.row{display:flex;align-items:center;gap:6px}
.stack{flex:1;min-width:0;display:flex;flex-direction:column;gap:4px}
.b{flex:1;min-width:0;border:1px solid #999;border-radius:6px;padding:6px 8px;background:#fafafa}
.id{display:block;font-size:11px;color:#666}
.c{background:#e1f5ee;border-color:#0f6e56}
.m{background:#fff;border:1.5px dashed #c0392b;color:#c0392b}
.te{background:#faeeda;border-color:#854f0b;text-align:center}
.hz{text-align:center}
.arrow{color:#999;flex:none}
.hd{color:#666;font-size:11px}
.hd span{flex:1}
.key{display:flex;gap:18px;margin:8px 0}
.key i{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:middle;margin-right:6px}
@media print{h2{page-break-before:always}}
"""


def e(text):
    """Make text safe to put inside a web page."""
    return html.escape(str(text))

def box(css_class, item_id, name, small=""):
    small_line = f'<span class="id">{e(small)}</span>' if small else ""
    return f'<div class="b {css_class}"><span class="id">{e(item_id)}</span>{e(name) or "(no name)"}{small_line}</div>'

def missing_box(text):
    return f'<div class="b m">&#9888; {e(text)}</div>'

def bowtie_to_html(bowtie):
    arrow = '<span class="arrow">&#8594;</span>'

    left = ['<div class="row hd"><span>Cause</span><span>Control (stops it)</span></div>']
    for cause in bowtie["causes"].values():
        rating = f'Rating: {cause["initial_rating"] or "?"} to {cause["residual_rating"] or "?"}'
        parts = [box("c", c["id"], c["name"], " | ".join(x for x in (c["hierarchy"], c["status"]) if x))
                 for c in cause["controls"].values()]
        parts += [missing_box(f'{c["id"]}: control type not recorded') for c in cause["untyped_controls"].values()]
        if not parts:
            parts = [missing_box("No control recorded")]
        left.append(f'<div class="row">{box("", cause["id"], cause["name"], rating)}{arrow}'
                    f'<div class="stack">{"".join(parts)}</div>{arrow}</div>')
    if not bowtie["causes"]:
        left.append(f'<div class="row">{missing_box("No causes recorded")}</div>')

    right = ['<div class="row hd"><span>Control (limits harm)</span><span>Consequence</span></div>']
    for consequence in bowtie["consequences"].values():
        parts = [box("c", c["id"], c["name"], " | ".join(x for x in (c["hierarchy"], c["status"]) if x))
                 for c in consequence["controls"].values()]
        if not parts:
            parts = [missing_box("No control recorded")]
        right.append(f'<div class="row">{arrow}<div class="stack">{"".join(parts)}</div>{arrow}'
                     f'{box("", consequence["id"], consequence["name"])}</div>')
    if not bowtie["consequences"]:
        right.append(f'<div class="row">{missing_box("No consequences recorded")}</div>')

    hazard_box = (f'<div class="b hz">{e(bowtie["hazard"])}</div>' if bowtie["hazard"]
                  else missing_box("No Context recorded"))
    middle = (f'<div class="hd">Hazard</div>{hazard_box}<div class="hd" style="text-align:center">&#8595;</div>'
              f'<div class="hd">Top event</div>'
              f'<div class="b te"><span class="id">{e(bowtie["id"])}</span>{e(bowtie["top_event"])}</div>')

    return (f'<h2 id="{e(bowtie["id"])}">{e(bowtie["id"])}: {e(bowtie["top_event"])}</h2>'
            f'<div class="bt"><div class="col">{"".join(left)}</div>'
            f'<div class="col">{middle}</div><div class="col">{"".join(right)}</div></div>')

def count_gaps(bowtie):
    """How many red boxes this bowtie will show."""
    gaps = 0 if bowtie["hazard"] else 1
    gaps += 1 if not bowtie["causes"] else 0
    gaps += 1 if not bowtie["consequences"] else 0
    for cause in bowtie["causes"].values():
        gaps += len(cause["untyped_controls"])
        if not cause["controls"] and not cause["untyped_controls"]:
            gaps += 1
    gaps += sum(1 for consequence in bowtie["consequences"].values() if not consequence["controls"])
    return gaps

def write_html(bowties, findings, source_name, path):
    levels = Counter(finding["Level"] for finding in findings)
    index_rows = []
    for bowtie in bowties.values():
        left_controls = sum(len(cause["controls"]) for cause in bowtie["causes"].values())
        right_controls = sum(len(c["controls"]) for c in bowtie["consequences"].values())
        index_rows.append(
            f'<tr><td><a href="#{e(bowtie["id"])}">{e(bowtie["id"])}</a></td><td>{e(bowtie["top_event"])}</td>'
            f'<td>{e(bowtie["hazard"])}</td><td>{len(bowtie["causes"])}</td><td>{left_controls}</td>'
            f'<td>{right_controls}</td><td>{len(bowtie["consequences"])}</td><td>{count_gaps(bowtie)}</td></tr>')
    page = (
        f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>Bowties</title><style>{PAGE_STYLE}</style></head><body>'
        f'<h1>Bowties built from {e(source_name)}</h1>'
        f'<p class="sub">{len(bowties)} bowties. Checks found: {levels["Must fix"]} must fix, '
        f'{levels["Review"]} to review, {levels["Info"]} for information. Details are in checks.xlsx.</p>'
        f'<div class="key"><span><i style="background:#e1f5ee;border:1px solid #0f6e56"></i>Control</span>'
        f'<span><i style="background:#faeeda;border:1px solid #854f0b"></i>Top event</span>'
        f'<span><i style="border:1.5px dashed #c0392b"></i>Missing in the workbook</span></div>'
        f'<table><tr><th>ID</th><th>Top event</th><th>Hazard</th><th>Causes</th><th>Controls left</th>'
        f'<th>Controls right</th><th>Consequences</th><th>Red boxes</th></tr>{"".join(index_rows)}</table>'
        f'{"".join(bowtie_to_html(bowtie) for bowtie in bowties.values())}</body></html>')
    Path(path).write_text(page, encoding="utf-8")
