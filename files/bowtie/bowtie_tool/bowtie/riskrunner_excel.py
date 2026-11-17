"""
riskrunner_excel.py
Writes the bowties as an Excel file in the SAME layout that Riskrunner's own
"export" produces (riskrunner_import.xlsx), so that it can be brought in with
Riskrunner's "import" by hand. No login or password is involved.

The layout was learned from a real export. It is one sheet called "Entities".
Each row is one box, and each box points at the box it hangs under:

    Entity         what kind of box: BowTieGroup, Hazard, TopEvent, Threat,
                   Consequence or BowTieControl
    Id             a unique code for this row
    ParentId       the Id of the row it hangs under
    Code           left empty (it was empty in the export)
    Name           the wording
    Description    left empty

    BowTieGroup
      Hazard
        TopEvent
          Threat          (a cause)
            BowTieControl (a control that stops it)
          Consequence
            BowTieControl (a control that limits the harm)

STATUS: the layout matches the export exactly, but importing this file has not
been tried yet. Only ever import it into a NEW, EMPTY assessment.
"""

import uuid
import warnings

import openpyxl

from bowtie.riskrunner_file import make_tree
from bowtie.workbook import GuidedStop

BASE_COLUMNS = ["Entity", "Id", "ParentId", "Code", "Name", "Description"]


def read_export(path):
    """From an export of the target assessment, take its column headings and its BowTieGroup Id."""
    warnings.simplefilter("ignore")
    workbook = openpyxl.load_workbook(path, data_only=True)
    if "Entities" not in workbook.sheetnames:
        raise GuidedStop(f'"{path}" does not look like a Riskrunner export: it has no sheet called "Entities".')
    rows = list(workbook["Entities"].iter_rows(values_only=True))
    headings = [h for h in rows[0] if h is not None]
    group_id = next((row[1] for row in rows[1:] if row[0] == "BowTieGroup"), None)

    # Safety: the file made here is meant for a NEW, EMPTY assessment only. If the export already
    # holds hazards, it came from an assessment that is in use, so refuse to build a file aimed at it.
    in_use = [row[4] for row in rows[1:] if row[0] == "Hazard"]
    if in_use:
        raise GuidedStop(f'"{path}" is an export of an assessment that already holds {len(in_use)} hazards '
                         f'(for example "{in_use[0]}").\n'
                         "To protect other people's work, the import file is only made for a NEW, EMPTY assessment.\n"
                         "Create a new assessment in Riskrunner, export that one, and use that export here.")
    return headings, group_id


def write_import_file(bowties, path, export_of_target=None):
    """Write every bowtie. Used by build_bowties.py."""
    write_import_rows(make_tree(bowties)["hazards"], path, export_of_target)


def write_import_rows(hazards, path, export_of_target=None):
    """Write the given hazards (all of them, or a chosen few) in Riskrunner's export layout."""
    headings, group_id = BASE_COLUMNS, None
    if export_of_target:
        headings, group_id = read_export(export_of_target)

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Entities"
    sheet.append(headings)

    def add(entity, parent_id, name):
        """Write one row and return its new Id, so its children can point at it."""
        row_id = str(uuid.uuid4())                     # a fresh Id that cannot clash with an existing one
        row = {"Entity": entity, "Id": row_id, "ParentId": parent_id, "Name": name}
        sheet.append([row.get(heading) for heading in headings])
        return row_id

    if group_id:                                       # reuse the target assessment's own group row
        sheet.append([{"Entity": "BowTieGroup", "Id": group_id}.get(heading) for heading in headings])
    else:
        group_id = add("BowTieGroup", None, None)

    for hazard in hazards:
        hazard_id = add("Hazard", group_id, hazard["element_name"])
        for top_event in hazard["top_events"]:
            top_event_id = add("TopEvent", hazard_id, top_event["element_name"])
            for threat in top_event["threats"]:
                threat_id = add("Threat", top_event_id, threat["element_name"])
                for control in threat["barriers"]:
                    add("BowTieControl", threat_id, control["element_name"])
            for consequence in top_event["consequences"]:
                consequence_id = add("Consequence", top_event_id, consequence["element_name"])
                for control in consequence["barriers"]:
                    add("BowTieControl", consequence_id, control["element_name"])

    for letter, width in zip("ABCDEF", (16, 38, 38, 8, 70, 14)):
        sheet.column_dimensions[letter].width = width
    workbook.save(path)
