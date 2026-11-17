"""
report.py
Writes the findings to an Excel file (checks.xlsx) with two sheets:
    Checks   one line per finding
    Summary  how many findings of each kind
"""

from collections import Counter

import openpyxl

from bowtie.checks import COLUMNS, LEVEL_ORDER


def write_checks(findings, path):
    workbook = openpyxl.Workbook()

    sheet = workbook.active
    sheet.title = "Checks"
    sheet.append(COLUMNS)
    for finding in findings:
        sheet.append([finding[column] for column in COLUMNS])
    for letter, width in zip("ABCDEFGH", (10, 30, 20, 10, 32, 70, 16, 70)):
        sheet.column_dimensions[letter].width = width
    sheet.freeze_panes = "A2"                  # keep the headings in view when scrolling
    sheet.auto_filter.ref = sheet.dimensions   # filter buttons on every column

    summary = workbook.create_sheet("Summary")
    summary.append(["Level", "Check", "Found in sheet", "Count"])
    counts = Counter((f["Level"], f["Check"], f["Found in sheet"]) for f in findings)
    for (level, check, found_sheet), count in sorted(counts.items(),
                                                      key=lambda item: (LEVEL_ORDER[item[0][0]], item[0][1], item[0][2])):
        summary.append([level, check, found_sheet, count])
    for letter, width in zip("ABCD", (10, 34, 20, 8)):
        summary.column_dimensions[letter].width = width

    workbook.save(path)
