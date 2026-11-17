"""
inspect_workbook.py  -  run this FIRST on a hazard log you have not used before.

    python inspect_workbook.py "Other project.xlsx"

It lists every sheet and its column headings, and writes a first guess at the
mapping to "mapping_suggested.json". The guess is made from the wording of the
headings. A PERSON MUST CHECK IT before it is used: copy it to a new name,
correct it, then run
    python build_bowties.py "Other project.xlsx" --mapping your_file.json

Nothing in the workbook is changed.
"""

import json
import sys
import warnings
from pathlib import Path

import openpyxl

from bowtie.workbook import clean, loose

# Words that suggest what a heading means. The first match wins, so order matters.
REGISTER_HINTS = [
    ("control_type", ["control type", "type of control", "barrier type"]),
    ("control_hierarchy", ["hierarchy"]),
    ("control_owner", ["owner"]),
    ("control_status", ["control status", "status"]),
    ("initial_likelihood", ["initial likelihood", "inherent likelihood"]),
    ("initial_consequence", ["initial consequence", "inherent consequence"]),
    ("initial_rating", ["initial rating", "inherent rating", "initial risk", "inherent risk"]),
    ("residual_likelihood", ["residual likelihood"]),
    ("residual_consequence", ["residual consequence"]),
    ("residual_rating", ["residual rating", "residual risk"]),
    ("control", ["control", "barrier", "safeguard", "mitigation"]),
    ("consequence", ["consequence", "outcome", "effect"]),
    ("cause", ["cause", "threat"]),
    ("top_event", ["top event", "loss of control", "hazardous event", "hazard"]),
    ("hazard", ["context", "activity", "hazard category"]),
]


def headings_of(sheet):
    """Guess the header row: the row in the first 40 with the most text cells."""
    best = []
    for row in sheet.iter_rows(min_row=1, max_row=40, values_only=True):
        texts = [clean(cell) for cell in row if isinstance(cell, str) and clean(cell)]
        if len(texts) > len(best):
            best = texts
    return best


def main():
    if len(sys.argv) < 2:
        sys.exit('Usage: python inspect_workbook.py "path to the workbook.xlsx"')
    warnings.simplefilter("ignore")
    workbook = openpyxl.load_workbook(sys.argv[1], data_only=True)

    all_headings = {}
    for sheet in workbook.worksheets:
        all_headings[sheet.title] = headings_of(sheet)
        hidden = "" if sheet.sheet_state == "visible" else "  (hidden)"
        print(f'\nSheet "{sheet.title}"{hidden}: {sheet.max_row} rows')
        print("   " + " | ".join(all_headings[sheet.title][:30]) if all_headings[sheet.title] else "   (no headings found)")

    # The register is guessed as the sheet whose headings cover the most of what a bowtie needs.
    def guess(headings):
        found = {}
        # Headings that look like reference numbers ("Cause Ref", "Hazard ID") are tried last,
        # because the wanted column is usually the one holding the wording.
        looks_like_reference = lambda h: any(w in loose(h).split() for w in ("ref", "id", "no", "number"))
        ordered = sorted(headings, key=looks_like_reference)
        for key, words in REGISTER_HINTS:
            for heading in ordered:
                if heading in found.values():
                    continue
                if any(word in loose(heading) for word in words):
                    found[key] = heading
                    break
        return found

    guesses = {name: guess(headings) for name, headings in all_headings.items()}
    best_sheet = max(guesses, key=lambda name: (all(k in guesses[name] for k in ("top_event", "cause", "control")),
                                                len(guesses[name])))
    register = {"sheet": best_sheet}
    for key, _ in REGISTER_HINTS:
        register[key] = guesses[best_sheet].get(key, "")

    suggestion = {
        "_read_me": ["This is a GUESS made from the wording of the headings. A person must check every line.",
                     "Lookup tabs (hazards_tab, causes_tab, controls_tab, consequences_tab) are not guessed.",
                     "Copy them from mapping.json if this workbook has such tabs."],
        "register": register,
        "left_side_words": ["Preventative", "Preventive", "Prevention"],
        "right_side_words": ["Mitigative", "Mitigating", "Mitigation", "Recovery"],
        "side_when_type_is_missing": "unknown",
    }
    Path("mapping_suggested.json").write_text(json.dumps(suggestion, indent=2), encoding="utf-8")

    print(f'\nBest guess for the register sheet: "{best_sheet}"')
    for key, heading in register.items():
        if key != "sheet":
            print(f'   {key:22} -> {heading or "(not found)"}')
    print("\nThe guess is saved as mapping_suggested.json. Check every line before using it.")


if __name__ == "__main__":
    main()
