"""
load_into_riskrunner.py  -  STEP 2 (needs your Riskrunner login)

Puts the bowties from "bowtie_output/riskrunner_tree.json" into a NEW assessment
that this program creates. It cannot write to any existing assessment.

    python load_into_riskrunner.py                         # practice run: shows the plan, sends nothing
    python load_into_riskrunner.py --send --only WS3-HAZ-030   # really load ONE bowtie
    python load_into_riskrunner.py --send --all                # really load all of them
    python load_into_riskrunner.py --send --only WS3-HAZ-030 --method import   # same, by uploading an Excel file

Run build_bowties.py first. Needs: requests (pip install requests).
Your password is typed at the prompt each time. It is never saved.
"""

import argparse
import getpass
import sys
from pathlib import Path

from bowtie.settings import OUTPUT_FOLDER, RISKRUNNER_API
from bowtie.loader import read_tree, choose, describe, run_load, save_log
from bowtie.riskrunner_api import SafeRiskrunner, SafetyError, RiskrunnerError, ALLOWED_CALLS


def main():
    parser = argparse.ArgumentParser(description="Load bowties into a new Riskrunner assessment.")
    parser.add_argument("--send", action="store_true", help="really send (without this, nothing is sent)")
    parser.add_argument("--only", metavar="HAZARD_ID", help="load just this one bowtie, e.g. WS3-HAZ-030")
    parser.add_argument("--all", action="store_true", help="load every bowtie")
    parser.add_argument("--method", choices=["messages", "import"], default="messages",
                        help='"messages" sends each hazard as a message (default); '
                             '"import" uploads an Excel import file, as a person would with Import')
    options = parser.parse_args()

    if options.send and not (options.only or options.all):
        sys.exit("STOPPED: with --send, say what to load: --only WS3-HAZ-030 (one bowtie) or --all.")

    tree_file = Path(OUTPUT_FOLDER) / "riskrunner_tree.json"
    if not tree_file.exists():
        sys.exit(f"STOPPED: {tree_file} not found. Run build_bowties.py first.")

    hazards = choose(read_tree(tree_file), options.only)
    if not hazards:
        sys.exit(f"STOPPED: no bowtie found with the ID {options.only}")

    print("PLAN")
    print(f"  Riskrunner address: {RISKRUNNER_API}")
    print("  A NEW assessment will be created. No existing assessment is opened or changed.")
    print("  Method: " + ("upload an Excel import file" if options.method == "import"
                          else 'send "add hazard" messages'))
    print("  What would be loaded:")
    print("\n".join(describe(hazards)))
    print("  The only kinds of message this program can send:")
    for method, path in ALLOWED_CALLS:
        print(f"    {method:4} {path}")

    if not options.send:
        print("\nPRACTICE RUN: nothing was sent. Add --send to do it for real.")
        return
    if input('\nType YES to create the new assessment and load this: ').strip() != "YES":
        sys.exit("Stopped. Nothing was sent.")
    email = input("Riskrunner email: ").strip()
    password = getpass.getpass("Riskrunner password (hidden as you type): ")

    client = SafeRiskrunner()
    log_file = Path(OUTPUT_FOLDER) / "riskrunner_log.json"
    try:
        address = run_load(client, hazards, email, password, method=options.method)
        print(f"\nDONE. Open this in your browser to look at the result:\n  {address}")
        print("To remove the test assessment afterwards, delete it by hand in Riskrunner.")
    except SafetyError as error:
        print(f"\nSAFETY STOP: {error}")
    except RiskrunnerError as error:
        print(f"\nRISKRUNNER SAID NO: {error}")
        print("Nothing outside the new test assessment was touched.")
    except PermissionError as error:
        print(f"\nSTOPPED: {error}")
    finally:
        save_log(client, log_file)
        print(f"A record of every message sent is in {log_file} (no password or token in it).")


if __name__ == "__main__":
    main()
