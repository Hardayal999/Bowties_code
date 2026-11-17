"""
checks.py
Looks for everything that is missing or does not match, and lists it.

Each finding is one line with eight columns:
    Level           Must fix / Review / Info
    Check           the kind of problem
    Found in sheet  the sheet where the problem can be seen
    Excel row       the row on that sheet
    Item            the ID (or name) concerned
    Problem         what is wrong
    Fix in sheet    the sheet where the correction should be made
    How to fix      what to do

A check only runs when the workbook has what that check needs. For example,
"name differs between sheets" is skipped for a project that has no Controls tab.
"""

from collections import Counter

from bowtie.builder import which_side
from bowtie.workbook import split_ids

COLUMNS = ["Level", "Check", "Found in sheet", "Excel row", "Item", "Problem", "Fix in sheet", "How to fix"]
LEVEL_ORDER = {"Must fix": 0, "Review": 1, "Info": 2}


def run_checks(data, bowties, mapping):
    findings = []
    already_listed = set()
    register_sheet = data["sheet_names"]["register"]

    def sheet(short):
        """The real name of a sheet in this workbook, or the register if the project has no such tab."""
        return data["sheet_names"].get(short) or register_sheet

    def has(short, key=None):
        """Does this workbook have that tab (and that column on it)?"""
        if not data["sheet_names"].get(short):
            return False
        return key is None or key in data["headings"][short]

    def heading(short, key):
        """The workbook's own heading for a column, in quotation marks, for use in messages."""
        return f'"{data["headings"].get(short, {}).get(key, key.replace("_", " "))}"'

    def add(level, check, found_sheet, row, item, problem, fix_sheet, fix):
        # The same problem can show up on many register rows. List it once, at the first row.
        key = (check, item, problem, None if found_sheet == register_sheet else row)
        if key in already_listed:
            return
        already_listed.add(key)
        findings.append({"Level": level, "Check": check, "Found in sheet": found_sheet, "Excel row": row,
                         "Item": item, "Problem": problem, "Fix in sheet": fix_sheet, "How to fix": fix})

    # Anything the reader had to carry on without is reported first, so nothing is silent.
    for note in data["notes"]:
        add("Info", "Not found in this workbook", "(mapping.json)", "", "", note,
            "(mapping.json)", "If your workbook has it under another name, put that name in mapping.json.")

    # Look-up tables: ID -> the row it sits on in its own tab (empty when the project has no such tab).
    hazards = {row["id"]: row for row in data["hazards"] if row["id"]}
    causes = {row["id"]: row for row in data["causes"] if row["id"]}
    controls = {row["id"]: row for row in data["controls"] if row["id"]}
    consequences = {row["id"]: row for row in data["consequences"] if row["id"]}

    # Is there a control type column anywhere? If not, say so once, not once per control.
    type_column_exists = "control_type" in data["headings"]["register"] or has("controls", "type")
    side_default = which_side("", mapping)
    if not type_column_exists and side_default == "unknown":
        add("Must fix", "No control type column", "(mapping.json)", "", "",
            "No column says whether a control prevents or mitigates, so no control can be placed on a side.",
            "(mapping.json)", 'Map the column under "control_type", or set "side_when_type_is_missing" to "left".')
    elif not type_column_exists:
        add("Info", "No control type column", "(mapping.json)", "", "",
            f'No column says whether a control prevents or mitigates. Every control was placed on the {side_default}, '
            "as mapping.json says.", "(mapping.json)", "Check that this is what the project intends.")
    type_already_reported = set()

    # --- 1. Checks on the lookup tabs (skipped for projects without them) -----
    for row in data["controls"]:
        label = row["id"] or row["name"]
        where = sheet("controls")
        if not row["id"]:
            add("Must fix", "Control has no ID", where, row["_row"], label,
                "The control cannot be linked to anything.", where, f'Fill in {heading("controls", "id")}.')
            continue
        if has("controls", "name") and not row["name"]:
            add("Must fix", "Control has no name", where, row["_row"], label,
                "The box would be blank.", where, f'Fill in {heading("controls", "name")}.')
        if has("controls", "type"):
            side = which_side(row["type"], mapping)
            if side == "unknown":
                type_already_reported.add(row["id"])
            if not row["type"] and side == "unknown":
                add("Must fix", "Control has no type", where, row["_row"], label,
                    "The program cannot tell which side of the bowtie it belongs on.",
                    where, f'Fill in {heading("controls", "type")}.')
            elif side == "unknown":
                add("Must fix", "Control type not recognised", where, row["_row"], label,
                    f'"{row["type"]}" is not a word the program knows.',
                    "(mapping.json)", 'Correct the word, or add it to "left_side_words" or "right_side_words".')
        if has("controls", "cause_ids"):
            if not split_ids(row["cause_ids"]):
                add("Review", "Control linked to no cause", where, row["_row"], label,
                    "The control appears in no bowtie.", where,
                    f'Fill in {heading("controls", "cause_ids")}, or delete the control.')
            for cause_id in split_ids(row["cause_ids"]):
                if has("causes") and cause_id not in causes:
                    add("Must fix", "Unknown ID", where, row["_row"], label,
                        f'Points to cause {cause_id}, which is not on the "{sheet("causes")}" sheet.',
                        where, "Correct the ID. Separate several IDs with commas.")

    for row in data["causes"]:
        where = sheet("causes")
        if has("causes", "top_event_ids"):
            if not split_ids(row["top_event_ids"]):
                add("Review", "Cause linked to no hazard", where, row["_row"], row["id"],
                    "The cause appears in no bowtie.", where, f'Fill in {heading("causes", "top_event_ids")}.')
            for top_event_id in split_ids(row["top_event_ids"]):
                if has("hazards") and top_event_id not in hazards:
                    add("Must fix", "Unknown ID", where, row["_row"], row["id"],
                        f'Points to {top_event_id}, which is not on the "{sheet("hazards")}" sheet.',
                        where, "Correct the ID. Separate several IDs with commas.")
        for consequence_id in split_ids(row["consequence_ids"]):
            if has("consequences") and consequence_id not in consequences:
                add("Must fix", "Unknown ID", where, row["_row"], row["id"],
                    f'Points to consequence {consequence_id}, which is not on the "{sheet("consequences")}" sheet.',
                    where, "Correct the ID. Separate several IDs with commas.")

    # The same name on several IDs matters later: Riskrunner matches boxes by name.
    for short in ("causes", "controls"):
        ids_by_name = {}
        for row in data[short]:
            if row["id"] and row["name"]:
                ids_by_name.setdefault(row["name"], []).append(row["id"])
        for name, ids in ids_by_name.items():
            if len(ids) > 1:
                add("Info", "Same name on several IDs", sheet(short), "", name,
                    f"{len(ids)} IDs share this name: {', '.join(ids[:6])}{' ...' if len(ids) > 6 else ''}",
                    sheet(short), "Fine if intended. The program keeps them apart by putting the ID in front of the name.")

    # --- 2. Checks on the register sheet, row by row -------------------------
    seen_rows = Counter()
    ratings_per_cause = {}
    for row in data["register"]:
        excel_row = row["_row"]
        row_key = (row["top_event_id"], row["cause_id"], row["consequence_id"], row["control_id"])
        if not any(row_key):
            continue
        seen_rows[row_key] += 1
        if seen_rows[row_key] == 2:
            add("Info", "Duplicate row", register_sheet, excel_row, " / ".join(k for k in row_key if k),
                "The same hazard, cause, consequence and control appear more than once.",
                register_sheet, "Remove the repeat.")

        for item, short, required in (("top_event", "hazards", True), ("cause", "causes", True),
                                      ("consequence", "consequences", "consequence" in data["headings"]["register"]),
                                      ("control", "controls", False)):
            item_id, name = row[item + "_id"], row[item + "_name"]
            what = item.replace("_", " ")
            if not item_id:
                if required:
                    add("Must fix", f"Row has no {what}", register_sheet, excel_row,
                        row["cause_id"] or row["top_event_id"], f"The {what} cell is empty.",
                        register_sheet, f"Fill in the {what}.")
                continue
            if not has(short):
                continue                                    # no tab to compare with in this project
            table = {"hazards": hazards, "causes": causes, "consequences": consequences, "controls": controls}[short]
            if item_id not in table:
                add("Must fix", "Unknown ID", register_sheet, excel_row, item_id,
                    f'This {what} ID is not on the "{sheet(short)}" sheet.', sheet(short),
                    "Add it to that sheet, or correct the ID.")
            elif has(short, "name") and table[item_id]["name"] != name:
                add("Review", "Name differs between sheets", register_sheet, excel_row, item_id,
                    f'Register says "{name}", the "{sheet(short)}" sheet says "{table[item_id]["name"]}".',
                    sheet(short), "Make the two the same.")

        control_id = row["control_id"]
        if control_id and control_id in controls:
            tab_row = controls[control_id]
            for register_key, tab_key in (("control_type", "type"), ("control_hierarchy", "hierarchy"),
                                          ("control_owner", "owner"), ("control_status", "status")):
                if (register_key in data["headings"]["register"] and has("controls", tab_key)
                        and row[register_key] != tab_row[tab_key]):
                    add("Review", "Value differs between sheets", register_sheet, excel_row, control_id,
                        f'{heading("controls", tab_key)}: register says "{row[register_key]}", '
                        f'the "{sheet("controls")}" sheet says "{tab_row[tab_key]}".',
                        sheet("controls"), "Make the two the same.")
            if has("controls", "cause_ids") and row["cause_id"] and row["cause_id"] not in split_ids(tab_row["cause_ids"]):
                add("Review", "Link differs between sheets", register_sheet, excel_row, control_id,
                    f'Register links it to cause {row["cause_id"]}; the "{sheet("controls")}" sheet does not.',
                    sheet("controls"), f'Add the cause to {heading("controls", "cause_ids")}, or correct the register.')
        if (control_id and type_column_exists and control_id not in type_already_reported
              and which_side(row["control_type"], mapping) == "unknown"):
            problem = ("The program cannot tell which side of the bowtie it belongs on."
                       if not row["control_type"] else f'"{row["control_type"]}" is not a word the program knows.')
            add("Must fix", "Control has no type" if not row["control_type"] else "Control type not recognised",
                register_sheet, excel_row, control_id, problem, register_sheet,
                "Fill in the control type, or see the side settings in mapping.json.")

        if row["cause_id"]:
            rating = (row["initial_likelihood"], row["initial_consequence"],
                      row["residual_likelihood"], row["residual_consequence"])
            if any(rating):
                ratings_per_cause.setdefault(row["cause_id"], set()).add(rating)

    for cause_id, ratings in ratings_per_cause.items():
        if len(ratings) > 1:
            add("Review", "Ratings disagree", register_sheet, "", cause_id,
                f"This cause has {len(ratings)} different sets of ratings across its rows.",
                sheet("causes"), "Decide which is right and make the rows match.")

    # --- 3. Checks on the finished bowties ----------------------------------
    if bowties and not any(bowtie["hazard"] for bowtie in bowties.values()):
        add("Review", "No hazard box anywhere", "(mapping.json)", "", "",
            "No column is mapped as the hazard, so every bowtie has an empty hazard box.",
            "(mapping.json)", 'Put the right heading next to "hazard" under "register" or "hazards_tab".')
    for bowtie in bowties.values():
        hazard_row = hazards.get(bowtie["id"], {}).get("_row", "")
        if not bowtie["hazard"] and any(b["hazard"] for b in bowties.values()):
            add("Must fix", "Top event has no hazard", sheet("hazards"), hazard_row, bowtie["id"],
                "The bowtie has no hazard box.", sheet("hazards"), "Fill in the hazard for this top event.")
        if not bowtie["causes"]:
            add("Review", "Hazard has no causes", sheet("hazards"), hazard_row, bowtie["id"],
                "The bowtie is empty.", sheet("causes"), "Link causes to this top event.")
            continue
        for cause in bowtie["causes"].values():
            cause_row = causes.get(cause["id"], {}).get("_row", "")
            item = f'{bowtie["id"]} / {cause["id"]}'
            if not cause["controls"] and not cause["untyped_controls"]:
                note = "" if cause["in_register"] else " It is also not shown in the register sheet."
                add("Review", "Cause has no control", sheet("causes"), cause_row, item,
                    "Nothing is recorded that stops this cause." + note,
                    sheet("controls"), "Link a control to this cause, or record why none is needed.")
            if not cause["consequence_ids"]:
                add("Review", "Cause has no consequence", sheet("causes"), cause_row, item,
                    "No harm is recorded for this cause.", sheet("causes"), "Link a consequence to this cause.")
        if not any(consequence["controls"] for consequence in bowtie["consequences"].values()):
            add("Info", "No control on the right side", sheet("hazards"), hazard_row, bowtie["id"],
                "Nothing is recorded that limits the harm after the top event.",
                sheet("controls"), "Check whether a control that limits harm should exist.")

    findings.sort(key=lambda f: (LEVEL_ORDER[f["Level"]], f["Check"], f["Found in sheet"], str(f["Item"])))
    return findings
