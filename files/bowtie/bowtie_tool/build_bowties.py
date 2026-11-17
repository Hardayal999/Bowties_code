"""
build_bowties.py  -  STEP 1 (works offline, touches nothing)

Reads a hazard log workbook, builds one bowtie per top event, checks them,
and writes the results into the folder "bowtie_output".

    python build_bowties.py "Project_HL_FOR_CODE.xlsx"
    python build_bowties.py "Other project.xlsx" --mapping other_project.json
    python build_bowties.py "Project_HL_FOR_CODE.xlsx" --no-preview
    python build_bowties.py "Project_HL_FOR_CODE.xlsx" --riskrunner-export "export of my empty assessment.xlsx"

Where things are in the workbook is described in mapping.json, not in the code.
Needs: Python 3.9 or newer, and openpyxl (pip install openpyxl).
"""

import argparse
import sys
import traceback
from collections import Counter
from pathlib import Path

from bowtie.settings import OUTPUT_FOLDER, MAPPING_FILE
from bowtie.workbook import read_mapping, read_workbook, GuidedStop
from bowtie.builder import build_bowties
from bowtie.checks import run_checks
from bowtie.report import write_checks
from bowtie.preview import write_html
from bowtie.riskrunner_file import write_riskrunner
from bowtie.riskrunner_excel import write_import_file, read_export


def run(options):
    workbook_path = Path(options.workbook)
    if not workbook_path.exists():
        raise GuidedStop(f'Cannot find the workbook "{workbook_path}". Check the name and the folder.')

    # Remove results from any earlier run first, so a stopped run can never leave old files looking current.
    output = Path(OUTPUT_FOLDER)
    for old_file in ("checks.xlsx", "riskrunner_tree.json", "riskrunner_import.xlsx", "bowties.html",
                     "error_report.txt"):
        (output / old_file).unlink(missing_ok=True)

    if options.riskrunner_export:                         # check this first, before anything is written
        if not Path(options.riskrunner_export).exists():
            raise GuidedStop(f'Cannot find the Riskrunner export "{options.riskrunner_export}".')
        read_export(options.riskrunner_export)

    mapping = read_mapping(options.mapping)               # 1. where things are in this workbook
    data = read_workbook(workbook_path, mapping)          # 2. read the sheets
    bowties = build_bowties(data, mapping)                # 3. turn rows into bowties
    findings = run_checks(data, bowties, mapping)         # 4. look for gaps and mismatches

    output.mkdir(exist_ok=True)                           # 5. write the results
    write_checks(findings, output / "checks.xlsx")
    write_riskrunner(bowties, output / "riskrunner_tree.json")
    write_import_file(bowties, output / "riskrunner_import.xlsx", options.riskrunner_export)
    if not options.no_preview:
        write_html(bowties, findings, workbook_path.name, output / "bowties.html")

    levels = Counter(finding["Level"] for finding in findings)
    print(f"Read {len(data['register'])} register rows from \"{data['sheet_names']['register']}\".")
    print(f"Built {len(bowties)} bowties.")
    print(f"Checks: {levels['Must fix']} must fix, {levels['Review']} to review, {levels['Info']} for information.")
    if data["notes"]:
        print(f"{len(data['notes'])} optional sheets or columns were not found. The program carried on without them;")
        print("they are listed at the bottom of checks.xlsx under \"Not found in this workbook\".")
    print(f"Files are in the folder: {output.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="Build bowties from a hazard log workbook.")
    parser.add_argument("workbook", help="path to the Excel workbook")
    parser.add_argument("--mapping", default=str(Path(__file__).parent / MAPPING_FILE),
                        help="the mapping file for this project (default: mapping.json)")
    parser.add_argument("--no-preview", action="store_true", help="skip the bowties.html preview page")
    parser.add_argument("--riskrunner-export", metavar="FILE",
                        help="an Excel export of the NEW, EMPTY Riskrunner assessment you will import into")
    options = parser.parse_args()

    try:
        run(options)
    except GuidedStop as stop:
        # Something essential is missing. Say what, and how to put it right.
        print("\nSTOPPED - nothing was written.\n")
        print(stop)
        sys.exit(2)
    except PermissionError:
        print("\nSTOPPED: a file is open in another program (probably checks.xlsx in Excel). Close it and run again.")
        sys.exit(2)
    except Exception:
        # Anything unexpected: no wall of code on screen. Save the details for whoever looks after the program.
        Path(OUTPUT_FOLDER).mkdir(exist_ok=True)
        report = Path(OUTPUT_FOLDER) / "error_report.txt"
        report.write_text(traceback.format_exc(), encoding="utf-8")
        print("\nSTOPPED: the program met something it did not expect in this workbook.")
        print(f"The technical details are saved in {report}. Send that file to whoever looks after the program.")
        sys.exit(1)


if __name__ == "__main__":
    main()
