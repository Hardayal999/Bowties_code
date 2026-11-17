"""
workbook.py
Opens the Excel workbook and turns it into tidy rows that always use the SAME
names, whatever the project's own headings are. mapping.json says which heading
means what.

After this file has run, the rest of the program never sees a project's own
column headings. That is what lets one program serve different hazard logs.

The workbook is only read. Nothing in it is changed.
"""

import difflib
import json
import re
import warnings
from pathlib import Path

import openpyxl

# The three things without which no bowtie can be drawn.
REQUIRED_IN_REGISTER = ["top_event", "cause", "control"]

TABS = ["hazards_tab", "causes_tab", "controls_tab", "consequences_tab"]

# Every name the rest of the program may ask a row for. A row always has all of
# them, blank when the workbook (or mapping.json) does not supply that column.
KNOWN_NAMES = {
    "register": ["top_event", "top_event_id", "hazard", "cause", "cause_id", "consequence", "consequence_id",
                 "control", "control_id", "control_type", "control_hierarchy", "control_owner", "control_status",
                 "initial_likelihood", "initial_consequence", "initial_rating",
                 "residual_likelihood", "residual_consequence", "residual_rating"],
    "hazards_tab": ["id", "name", "hazard"],
    "causes_tab": ["id", "name", "top_event_ids", "consequence_ids", "initial_rating", "residual_rating"],
    "controls_tab": ["id", "name", "type", "hierarchy", "owner", "status", "cause_ids"],
    "consequences_tab": ["id", "name"],
}


class GuidedStop(Exception):
    """Raised when something essential cannot be found. The message says what to do."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def clean(value):
    """Turn a cell value into tidy text. Empty cells become ''."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def loose(text):
    """Compare headings loosely: 'Control  Type:' and 'control type' count as the same."""
    return re.sub(r"[^a-z0-9]+", " ", clean(text).lower()).strip()


def split_id_name(cell):
    """'WS3-HAZ-001: Loss of control' -> ('WS3-HAZ-001', 'Loss of control')."""
    text = clean(cell)
    if ":" in text:
        left, right = text.split(":", 1)
        return left.strip(), right.strip()
    return text, ""


def split_ids(cell):
    """'WS3-HAZ-001, WS3-HAZ-005' -> ['WS3-HAZ-001', 'WS3-HAZ-005']. Commas or semicolons."""
    return [part.strip() for part in re.split(r"[,;]", clean(cell)) if part.strip()]


def as_list(value):
    """A mapping entry may be one heading or a list of possible headings."""
    if isinstance(value, list):
        return [v for v in value if clean(v)]
    return [value] if clean(value) else []


def read_mapping(path):
    """Read mapping.json. Lines starting with '_' are notes for people and are ignored."""
    path = Path(path)
    if not path.exists():
        raise GuidedStop(f'Cannot find the mapping file "{path}". It should sit next to build_bowties.py.')
    try:
        mapping = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise GuidedStop(f'The mapping file "{path}" has a typing mistake near line {error.lineno}: {error.msg}. '
                         "Check for a missing comma or quotation mark.")
    return {key: value for key, value in mapping.items() if not key.startswith("_")}


# ---------------------------------------------------------------------------
# Reading one sheet
# ---------------------------------------------------------------------------

def find_sheet(workbook, wanted_names):
    """Find a sheet by name, ignoring capitals and spacing. Returns the real name or None."""
    by_loose_name = {loose(name): name for name in workbook.sheetnames}
    for wanted in wanted_names:
        if loose(wanted) in by_loose_name:
            return by_loose_name[loose(wanted)]
    return None


def find_header_row(all_rows, wanted_headings):
    """The header row is the one, in the first 40 rows, holding the most wanted headings."""
    wanted = {loose(heading) for heading in wanted_headings}
    best_index, best_score = None, 0
    for index, row in enumerate(all_rows[:40]):
        score = len(wanted & {loose(cell) for cell in row if cell is not None})
        if score > best_score:
            best_index, best_score = index, score
    return best_index


def read_sheet(workbook, section, section_name, notes):
    """
    Read one sheet using its section of mapping.json.

    Returns (rows, real sheet name, headings found).
      rows            list of dictionaries keyed by OUR names, e.g. row["cause"]
      headings found  our name -> the workbook's real heading (for messages)
    A sheet or column that is not there gives empty results and a note. It never crashes.
    """
    sheet_name = find_sheet(workbook, as_list(section.get("sheet", "")))
    if sheet_name is None:
        if as_list(section.get("sheet", "")):
            notes.append(f'Sheet "{as_list(section["sheet"])[0]}" ({section_name}) was not found. '
                         "The program carried on without it.")
        return [], None, {}

    all_rows = list(workbook[sheet_name].iter_rows(values_only=True))
    wanted = {key: as_list(value) for key, value in section.items() if key != "sheet" and as_list(value)}
    header_index = find_header_row(all_rows, [h for headings in wanted.values() for h in headings])
    if header_index is None:
        notes.append(f'Sheet "{sheet_name}" has none of the headings listed for {section_name} in mapping.json.')
        return [], sheet_name, {}

    real_headings = [clean(cell) for cell in all_rows[header_index]]
    position = {}       # our name -> column number
    found = {}          # our name -> real heading
    for key, possible_headings in wanted.items():
        for heading in possible_headings:
            matches = [i for i, real in enumerate(real_headings) if real and loose(real) == loose(heading)]
            if matches:
                position[key], found[key] = matches[0], real_headings[matches[0]]
                break
        else:
            notes.append(f'Column "{possible_headings[0]}" ({section_name}: {key}) was not found on sheet '
                         f'"{sheet_name}". The program carried on without it.')

    rows = []
    for index in range(header_index + 1, len(all_rows)):
        values = all_rows[index]
        if all(cell is None for cell in values):
            continue
        row = {key: "" for key in KNOWN_NAMES[section_name]}      # every name exists, even if blank
        for key, column in position.items():
            row[key] = clean(values[column]) if column < len(values) else ""
        row["_row"] = index + 1                                   # the Excel row number
        rows.append(row)
    return rows, sheet_name, found


# ---------------------------------------------------------------------------
# Reading the whole workbook
# ---------------------------------------------------------------------------

def explain_missing(workbook, mapping, sheet_name, found, missing):
    """Build a helpful message when something essential is missing."""
    lines = ["The program could not find what it needs to draw bowties.", ""]
    if sheet_name is None:
        wanted = as_list(mapping.get("register", {}).get("sheet", ""))
        lines.append(f'It looked for the register sheet called "{wanted[0] if wanted else "(none given)"}".')
        lines.append("Sheets in this workbook: " + ", ".join(f'"{name}"' for name in workbook.sheetnames))
        close = difflib.get_close_matches(wanted[0] if wanted else "", workbook.sheetnames, n=1, cutoff=0.4)
        if close:
            lines.append(f'Closest match: "{close[0]}".')
        lines.append('Fix: open mapping.json and change "sheet" under "register" to the right name.')
    else:
        all_rows = list(workbook[sheet_name].iter_rows(values_only=True))
        seen = sorted({clean(cell) for row in all_rows[:40] for cell in row
                       if isinstance(cell, str) and 0 < len(clean(cell)) < 50})
        for key in missing:
            wanted = as_list(mapping["register"].get(key, ""))
            lines.append(f'It looked on sheet "{sheet_name}" for the {key.replace("_", " ")} column, '
                         f'called "{wanted[0] if wanted else "(nothing given in mapping.json)"}".')
            close = difflib.get_close_matches(wanted[0] if wanted else key, seen, n=3, cutoff=0.4)
            if close:
                lines.append("   Similar headings on that sheet: " + ", ".join(f'"{c}"' for c in close))
        lines.append("")
        lines.append('Fix: open mapping.json and put the right heading next to each of those names under "register".')
    lines.append("Tip: run  python inspect_workbook.py \"your workbook.xlsx\"  to list every sheet and heading.")
    return "\n".join(lines)


def split_register_row(row):
    """
    Work out the ID and the name of each item on a register row. Three layouts are understood:
      1. "ID: name" in one cell            (the layout of the sample workbook)
      2. ID and name in two separate columns
      3. a name only, with no ID           (the name is then used as the ID)
    """
    for item in ("top_event", "cause", "consequence", "control"):
        text, separate_id = row.get(item, ""), row.get(item + "_id", "")
        if separate_id:
            item_id, name = separate_id, text
        elif ":" in text:
            item_id, name = split_id_name(text)
        else:
            item_id, name = text, text
        row[item + "_id"], row[item + "_name"] = item_id, name
    return row


def read_workbook(path, mapping):
    """Open the workbook and return everything the rest of the program needs."""
    warnings.simplefilter("ignore")                          # openpyxl prints harmless notes
    workbook = openpyxl.load_workbook(path, data_only=True)  # data_only = formula results, not formulas
    notes = []

    register, register_sheet, register_found = read_sheet(workbook, mapping.get("register", {}), "register", notes)
    missing = [key for key in REQUIRED_IN_REGISTER if key not in register_found]
    if register_sheet is None or missing:
        raise GuidedStop(explain_missing(workbook, mapping, register_sheet, register_found, missing))

    data = {"register": [split_register_row(row) for row in register],
            "sheet_names": {"register": register_sheet},
            "headings": {"register": register_found},
            "notes": notes}
    for tab in TABS:
        rows, sheet_name, found = read_sheet(workbook, mapping.get(tab, {}), tab, notes)
        short = tab.replace("_tab", "")
        data[short] = [row for row in rows if any(value for key, value in row.items() if key != "_row")]
        data["sheet_names"][short] = sheet_name
        data["headings"][short] = found
    return data
