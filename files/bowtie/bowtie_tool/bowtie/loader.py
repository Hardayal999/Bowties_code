"""
loader.py
The steps that put bowties into Riskrunner, in order.
It only ever talks to Riskrunner through SafeRiskrunner (riskrunner_api.py).
"""

import json
import time
from datetime import datetime
from pathlib import Path

from bowtie.settings import OUTPUT_FOLDER, RISKRUNNER_SITE, SANDBOX_PREFIX
from bowtie.riskrunner_api import RiskrunnerError
from bowtie.riskrunner_excel import write_import_rows


def read_tree(path):
    """Read riskrunner_tree.json, the file made by build_bowties.py."""
    return json.loads(Path(path).read_text(encoding="utf-8"))["hazards"]


def choose(hazards, only_id=None):
    """Keep everything, or keep only the one bowtie whose ID was asked for."""
    if not only_id:
        return hazards
    chosen = []
    for hazard in hazards:
        top_events = [t for t in hazard["top_events"]
                      if t["element_name"] == only_id or t["element_name"].startswith(only_id + ":")]
        if top_events:
            chosen.append({"element_name": hazard["element_name"], "top_events": top_events})
    return chosen


def describe(hazards):
    """Count what would be sent, as plain text lines."""
    lines = []
    for hazard in hazards:
        lines.append(f'  Hazard: {hazard["element_name"]}')
        for top_event in hazard["top_events"]:
            causes = len(top_event["threats"])
            left = sum(len(t["barriers"]) for t in top_event["threats"])
            right = sum(len(c["barriers"]) for c in top_event["consequences"])
            lines.append(f'    {top_event["element_name"]}  '
                         f'({causes} causes, {left} controls left, {right} controls right, '
                         f'{len(top_event["consequences"])} consequences)')
    return lines


def run_load(client, hazards, email, password, method="messages", say=print, pause=time.sleep):
    """
    Do the real load into a NEW assessment. Returns the address of that assessment.

    method "messages": send each hazard as an "add hazard" message.
    method "import":   build an Excel import file and upload it, as a person would with Import.
    Steps 1 to 4 are the same for both.
    """
    say("1. Checking Riskrunner can be reached ...")
    client.is_reachable()

    say("2. Logging in ...")
    client.login(email, password)

    say("3. Checking who you are and what you may do ...")
    me = client.who_am_i()
    membership = me.get("active_tenant_membership") or {}
    say(f'   Logged in as {me.get("first_name", "")} {me.get("last_name", "")} ({me.get("email", "")})')
    if membership.get("can_add_assessments") is False:
        raise PermissionError("Your account is not allowed to create assessments. "
                              "Ask your Riskrunner administrator for that right.")

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    name = f'{SANDBOX_PREFIX} - {me.get("first_name") or "user"} - {stamp} - safe to delete'
    say(f'4. Creating a new, empty assessment called "{name}" ...')
    assessment = client.create_sandbox_assessment(
        name, "Created by the bowtie loader for testing. Contains test data only. Safe to delete.")
    address = f'{RISKRUNNER_SITE}/assessments/{assessment["id"]}'
    say(f"   Created: {address}")

    if method == "import":
        load_by_import(client, assessment, hazards, say, pause)
    else:
        load_by_messages(client, assessment, hazards, say)
    return address


def load_by_messages(client, assessment, hazards, say):
    say("5. Opening an editing session in that assessment ...")
    review = client.open_review(assessment["id"], "Bowtie load")

    say("6. Sending the bowties, one hazard at a time ...")
    for number, hazard in enumerate(hazards, start=1):
        client.add_hazard(review["id"], hazard)
        say(f'   {number} of {len(hazards)} sent: {hazard["element_name"]} '
            f'({len(hazard["top_events"])} bowties)')

    say("7. Reading back what the new assessment now holds ...")
    count = client.count_hazards(assessment["id"])
    say(f"   Riskrunner reports {count} hazards in the new assessment (sent: {len(hazards)}).")


def load_by_import(client, assessment, hazards, say, pause):
    file_path = Path(OUTPUT_FOLDER) / "riskrunner_import_sent.xlsx"
    say(f"5. Writing the import file {file_path} ...")
    file_path.parent.mkdir(exist_ok=True)
    write_import_rows(hazards, file_path)

    say("6. Uploading it into the new assessment ...")
    try:
        client.upload_import_file(assessment["id"], file_path)
    except RiskrunnerError as error:
        if error.status not in (400, 403, 409, 422):
            raise
        say("   Riskrunner did not accept it directly. Trying again inside an editing session ...")
        review = client.open_review(assessment["id"], "Bowtie import")
        client.upload_import_file(assessment["id"], file_path, review_id=review["id"])

    say("7. Waiting for Riskrunner to finish the import (it works in the background) ...")
    count = 0
    for _ in range(24):                       # look every 5 seconds, for up to 2 minutes
        count = client.count_hazards(assessment["id"]) or 0
        if count:
            break
        pause(5)
    if count:
        say(f"   Riskrunner reports {count} hazards in the new assessment (sent: {len(hazards)}).")
    else:
        say("   After 2 minutes Riskrunner still reports no hazards. The import may have been refused, "
            "or may still be running. Open the assessment in your browser to look.")


def save_log(client, path):
    """Write the record of every message sent. It holds no password and no token."""
    Path(path).write_text(json.dumps(client.log, indent=2), encoding="utf-8")
