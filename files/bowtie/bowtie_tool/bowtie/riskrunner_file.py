"""
riskrunner_file.py
Writes the bowties in the layout Riskrunner accepts (riskrunner_tree.json).

Riskrunner takes a whole tree in one message:
    hazard -> top events -> threats (causes) -> barriers (controls)
                         -> consequences     -> barriers (controls)

Every name carries its ID in front, for example
    "WS3-CAU-0001: Quantum coffee spill anomalies"
because Riskrunner matches boxes by name. Without the ID, two different
items with the same wording would merge into one box.
"""

import json
from pathlib import Path


def named(item):
    """'ID: name'. Just one of them if the other is empty, or if the project has no separate IDs."""
    if not item["name"] or item["name"] == item["id"]:
        return item["id"]
    return f'{item["id"]}: {item["name"]}'


def make_tree(bowties):
    """Group the bowties by hazard and return them as nested lists."""
    top_events_by_hazard = {}
    for bowtie in bowties.values():
        top_event = {
            "element_name": named({"id": bowtie["id"], "name": bowtie["top_event"]}),
            "threats": [
                {"element_name": named(cause),
                 "barriers": [{"element_name": named(control)} for control in cause["controls"].values()]}
                for cause in bowtie["causes"].values()],
            "consequences": [
                {"element_name": named(consequence),
                 "barriers": [{"element_name": named(control)} for control in consequence["controls"].values()]}
                for consequence in bowtie["consequences"].values()],
        }
        top_events_by_hazard.setdefault(bowtie["hazard"] or "(no Context)", []).append(top_event)

    return {"hazards": [{"element_name": hazard, "top_events": top_events}
                        for hazard, top_events in top_events_by_hazard.items()]}


def write_riskrunner(bowties, path):
    Path(path).write_text(json.dumps(make_tree(bowties), indent=2), encoding="utf-8")
