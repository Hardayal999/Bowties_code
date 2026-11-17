"""
builder.py
Turns the tidy rows into bowties.
The register sheet comes first. The other tabs, when a project has them,
fill in what the register leaves out.
"""

from bowtie.workbook import loose, split_ids


def new_bowtie(top_event_id, top_event_name):
    return {"id": top_event_id, "top_event": top_event_name, "hazard": "",
            "causes": {}, "consequences": {}}


def new_cause(cause_id, name):
    return {"id": cause_id, "name": name, "in_register": False,
            "initial_rating": "", "residual_rating": "",
            "controls": {},          # left-side controls
            "untyped_controls": {},  # controls whose side is unknown
            "consequence_ids": []}


def which_side(control_type, mapping):
    """'left', 'right' or 'unknown', from the control's type word and mapping.json."""
    word = loose(control_type)
    if not word:
        choice = loose(mapping.get("side_when_type_is_missing", "unknown"))
        return choice if choice in ("left", "right") else "unknown"
    if word in {loose(w) for w in mapping.get("left_side_words", [])}:
        return "left"
    if word in {loose(w) for w in mapping.get("right_side_words", [])}:
        return "right"
    return "unknown"


def build_bowties(data, mapping):
    """Return a dictionary: top event ID -> bowtie."""
    bowties = {}

    # Step A: walk down the register sheet, one row at a time.
    for row in data["register"]:
        if not row["top_event_id"]:
            continue
        bowtie = bowties.setdefault(row["top_event_id"], new_bowtie(row["top_event_id"], row["top_event_name"]))
        if row["hazard"] and not bowtie["hazard"]:
            bowtie["hazard"] = row["hazard"]                       # some projects keep the hazard on the register

        cause = None
        if row["cause_id"]:
            cause = bowtie["causes"].setdefault(row["cause_id"], new_cause(row["cause_id"], row["cause_name"]))
            cause["in_register"] = True
            cause["initial_rating"] = row["initial_rating"]
            cause["residual_rating"] = row["residual_rating"]

        consequence = None
        if row["consequence_id"]:
            consequence = bowtie["consequences"].setdefault(
                row["consequence_id"],
                {"id": row["consequence_id"], "name": row["consequence_name"], "controls": {}})
            if cause and row["consequence_id"] not in cause["consequence_ids"]:
                cause["consequence_ids"].append(row["consequence_id"])

        if row["control_id"]:
            control = {"id": row["control_id"], "name": row["control_name"], "type": row["control_type"],
                       "hierarchy": row["control_hierarchy"], "owner": row["control_owner"],
                       "status": row["control_status"]}
            side = which_side(control["type"], mapping)
            if side == "left" and cause:
                cause["controls"][control["id"]] = control             # left side, under its cause
            elif side == "right" and consequence:
                consequence["controls"][control["id"]] = control       # right side, before its consequence
            elif cause:
                cause["untyped_controls"][control["id"]] = control     # side unknown: keep it, flag it

    # Step B: use the other tabs, where the project has them.
    consequence_names = {row["id"]: row["name"] for row in data["consequences"]}

    for row in data["hazards"]:                      # every top event gets a bowtie, even with no rows
        if not row["id"]:
            continue
        bowtie = bowties.setdefault(row["id"], new_bowtie(row["id"], row["name"]))
        if row["hazard"]:
            bowtie["hazard"] = row["hazard"]

    for row in data["causes"]:                       # causes the register sheet does not show
        for top_event_id in split_ids(row["top_event_ids"]):
            bowtie = bowties.get(top_event_id)
            if bowtie is None or row["id"] in bowtie["causes"]:
                continue
            cause = new_cause(row["id"], row["name"])
            cause["initial_rating"] = row["initial_rating"]
            cause["residual_rating"] = row["residual_rating"]
            cause["consequence_ids"] = split_ids(row["consequence_ids"])
            bowtie["causes"][cause["id"]] = cause
            for consequence_id in cause["consequence_ids"]:
                bowtie["consequences"].setdefault(
                    consequence_id,
                    {"id": consequence_id, "name": consequence_names.get(consequence_id, ""), "controls": {}})

    return dict(sorted(bowties.items()))
