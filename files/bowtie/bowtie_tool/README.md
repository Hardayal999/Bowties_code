# Bowtie tool

Turns a hazard log workbook into bowties, checks them, and (optionally) loads
them into a NEW test assessment in Riskrunner.

## The steps

| Step | Command | Needs | Touches Riskrunner? |
| --- | --- | --- | --- |
| 0. Inspect (new workbooks only) | `python inspect_workbook.py "workbook.xlsx"` | openpyxl | No |
| 1. Build | `python build_bowties.py "workbook.xlsx"` | openpyxl | No |
| 2. Load | `python load_into_riskrunner.py` | requests, your login | Only with `--send` |

Install the two add-ons once:

    pip install openpyxl requests

## Step 1: build (offline)

    python build_bowties.py "Project_HL_FOR_CODE.xlsx"

Writes into the folder `bowtie_output`:

| File | What it is |
| --- | --- |
| bowties.html | A picture of every bowtie. Look at this before loading anything. |
| checks.xlsx | Every gap or mismatch: where it was found, where to fix it |
| riskrunner_import.xlsx | The bowties in the layout of Riskrunner's own Excel export, for importing by hand |
| riskrunner_tree.json | The bowties in the layout the loader program sends |

## Using a different project's hazard log

Where things are in a workbook is described in `mapping.json`, not in the code.
For a new project you edit a copy of that file. You do not edit the program.

1. Run `python inspect_workbook.py "Other project.xlsx"`. It lists every sheet
   and heading and writes a first guess to `mapping_suggested.json`.
2. Copy that file to a new name, for example `other_project.json`, and check
   every line. The guess comes from the wording of the headings and can be wrong.
3. Run `python build_bowties.py "Other project.xlsx" --mapping other_project.json`.

What the program copes with on its own:

| Difference | What happens |
| --- | --- |
| Sheets or columns have other names | Put the names in the mapping file |
| Capital letters, extra spaces, punctuation in a heading | Ignored |
| Title lines above the headings | The heading row is found automatically |
| No Hazards / Causes / Controls / Consequences tabs | It builds from the register sheet alone |
| A column is missing (ratings, owner, status, consequence) | It carries on and lists it in checks.xlsx |
| ID and name in one cell ("ID: name"), in two columns, or no IDs | All three are understood |
| No control type column | Reported once; or set `side_when_type_is_missing` to `left` |

Only three things are essential: a top event column, a cause column and a
control column. If one cannot be found, the program stops, says what it looked
for, shows the similar headings it did find, and tells you which line of the
mapping file to change. Nothing is written in that case.

What it does NOT cope with: a log with a different structure, for example
several controls typed into one cell, or preventive and mitigating controls in
two separate columns. That needs a change in `bowtie/workbook.py`. The other
files stay as they are.

## Step 2, route A: Riskrunner's own Excel import (by hand, no password)

`riskrunner_import.xlsx` has the same layout as a Riskrunner export: one sheet
called "Entities", one row per box, each row pointing at its parent row.

1. In Riskrunner, create a NEW assessment. Never use one that other people work in.
2. Export that new, empty assessment to Excel.
3. Run `python build_bowties.py "workbook.xlsx" --riskrunner-export "that export.xlsx"`.
   The program refuses an export that already holds hazards.
4. In the new assessment, use Import and choose `bowtie_output/riskrunner_import.xlsx`.

Status: the layout matches a real export, but the import itself has not been
tried. It is not known whether importing adds to an assessment or replaces
what is there, which is why it must only be tried on a new, empty one.

## Step 2, routes B and C: the loader program

    python load_into_riskrunner.py                             # practice run, sends nothing
    python load_into_riskrunner.py --send --only WS3-HAZ-030   # load ONE bowtie
    python load_into_riskrunner.py --send --all                # load all of them
    python load_into_riskrunner.py --send --only WS3-HAZ-030 --method import

Route B (the default, `--method messages`) sends each hazard as an "add hazard"
message. Route C (`--method import`) writes an Excel file in Riskrunner's export
layout and uploads it, which is what a person does with Import in route A.
Both create a new assessment and both obey the same safety rules.

It asks you to type YES, then your email and password. The password is not saved.
It always creates a new assessment named "SANDBOX bowtie test - ...".
To remove a test assessment afterwards, delete it by hand in Riskrunner.

## Trying the calls by hand in Postman

The folder `postman` holds a ready-made collection with one request for each
kind of message the loader sends. Import it into Postman, put your email and
password in the collection's Variables tab (Current value column only), and run
the requests in order. Postman has no safety gate of its own: only use the
requests in the collection.

## Safety

Run this any time. It needs no login and no internet:

    python test_safety.py

It proves that the program refuses to delete, rename or write to anything it
did not create in the same run. The rules are at the top of
`bowtie/riskrunner_api.py`.

## Where things are

| File | Job | Change it when |
| --- | --- | --- |
| mapping.json | Says where things are in the hazard log | Every new project (use a copy) |
| inspect_workbook.py | Lists a workbook's sheets and headings, guesses a mapping | Rarely |
| build_bowties.py | Runs step 1 | Rarely |
| load_into_riskrunner.py | Runs step 2 | Rarely |
| test_safety.py | Proves the safety rules hold | You add a new allowed call |
| postman/ | A Postman collection of every call the loader sends | Riskrunner's messages change |
| bowtie/settings.py | Output folder and the Riskrunner web address | The address changes |
| bowtie/workbook.py | Reads the Excel sheets using the mapping | A log has a different structure |
| bowtie/builder.py | Turns rows into bowties | The rule for placing a control changes |
| bowtie/checks.py | Finds gaps and mismatches | You want a new check |
| bowtie/report.py | Writes checks.xlsx | You want different columns |
| bowtie/preview.py | Writes bowties.html | You want a different look |
| bowtie/riskrunner_excel.py | Writes riskrunner_import.xlsx | Riskrunner's export layout changes |
| bowtie/riskrunner_file.py | Writes riskrunner_tree.json | Riskrunner's message layout changes |
| bowtie/riskrunner_api.py | The only file that talks to Riskrunner; holds the safety gate | Riskrunner's messages change |
| bowtie/loader.py | The loading steps, in order, for both methods | The order of steps changes |

## Status

Step 1 has been run on the sample workbook and on seven altered copies of it
(renamed sheets, renamed columns, missing tabs, missing columns, a blank
workbook). It has NOT been run on a second real project's hazard log.

Step 2 (routes B and C) has been rehearsed against a pretend Riskrunner only.
It has NOT yet been run against the real one, so expect the first real run to
need adjustments. Start with `--only` on one bowtie. Route A, importing by
hand, has not been tried either. The Postman collection has not been opened in
Postman; its guard script was tested on its own.
