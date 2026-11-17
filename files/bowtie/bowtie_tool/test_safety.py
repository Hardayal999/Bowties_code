"""
test_safety.py  -  proves the safety gate works. Runs offline; no login, no internet.

    python test_safety.py

It swaps the real "send" for a pretend one, then tries a series of messages.
Messages that could touch other people's work must be REFUSED before sending.
"""

import sys

from bowtie.riskrunner_api import SafeRiskrunner, SafetyError

SOMEONE_ELSES_ASSESSMENT = "328e2042-f3fe-44b8-b333-291470e8086b"
SOMEONE_ELSES_REVIEW = "11111111-2222-3333-4444-555555555555"
OUR_NEW_ASSESSMENT = "aaaaaaaa-0000-0000-0000-000000000001"
OUR_NEW_REVIEW = "bbbbbbbb-0000-0000-0000-000000000002"


class PretendRiskrunner:
    """Stands in for the real website. It records what reached it and gives canned replies."""

    def __init__(self, assessment_reply=None):
        self.received = []
        self.assessment_reply = assessment_reply
        self.imported = False

    def send(self, method, url, headers, json_body, form, params, upload=None):
        path = url.split("/api", 1)[1]
        self.received.append((method, path))
        if path == "/token":
            return 200, {"access_token": "pretend-token"}
        if (method, path) == ("POST", "/assessments"):
            return 200, self.assessment_reply or {
                "id": OUR_NEW_ASSESSMENT, "name": json_body["name"], "parent_id": None,
                "hazard_links": [], "hazard_elements": []}
        if path == "/users/me/context":
            return 200, {"first_name": "Test", "last_name": "User", "email": "someone@example.com",
                         "active_tenant_membership": {"can_add_assessments": True}}
        if path.endswith("/reviews"):
            return 200, {"id": OUR_NEW_REVIEW, "assessment_id": OUR_NEW_ASSESSMENT}
        if path.endswith("/import"):
            self.imported = True
            return 200, {"detail": "import started"}
        return 200, {"items": [{"id": "x"}] if self.imported else []}


results = []


def must_refuse(description, action, website):
    before = len(website.received)
    try:
        action()
        ok = False
    except SafetyError:
        ok = len(website.received) == before       # refused AND nothing reached the website
    results.append(ok)
    print(f'{"PASS" if ok else "FAIL"}  refused: {description}')


def must_allow(description, action):
    try:
        action()
        ok = True
    except SafetyError as error:
        ok = False
        description += f"  ({error})"
    results.append(ok)
    print(f'{"PASS" if ok else "FAIL"}  allowed: {description}')


# --- Before anything has been created, every ID belongs to someone else -------
site = PretendRiskrunner()
client = SafeRiskrunner(send=site.send)
client.login("someone@example.com", "not-a-real-password")

must_refuse("delete an existing assessment",
            lambda: client.call("DELETE", f"/assessments/{SOMEONE_ELSES_ASSESSMENT}"), site)
must_refuse("rename an existing assessment",
            lambda: client.call("PUT", f"/assessments/{SOMEONE_ELSES_ASSESSMENT}", json_body={"name": "x"}), site)
must_refuse("open a review in an existing assessment",
            lambda: client.open_review(SOMEONE_ELSES_ASSESSMENT, "x"), site)
must_refuse("add a hazard through someone else's review",
            lambda: client.add_hazard(SOMEONE_ELSES_REVIEW, {"element_name": "x"}), site)
must_refuse("change someone else's review",
            lambda: client.call("PUT", f"/reviews/{SOMEONE_ELSES_REVIEW}", json_body={"status": "finished"}), site)
must_refuse("delete a hazard in someone else's review",
            lambda: client.call("DELETE", f"/reviews/{SOMEONE_ELSES_REVIEW}/elements/hazards/{SOMEONE_ELSES_REVIEW}"), site)
must_refuse("import an Excel file into an existing assessment",
            lambda: client.call("POST", f"/assessments/{SOMEONE_ELSES_ASSESSMENT}/import"), site)
must_refuse("read the list of all assessments",
            lambda: client.call("GET", "/assessments"), site)
must_refuse("create or remove users",
            lambda: client.call("POST", "/users", json_body={}), site)

# --- The normal path: create our own, then work only inside it ----------------
must_allow("create one new assessment",
           lambda: client.create_sandbox_assessment("SANDBOX test", "test"))
must_allow("open a review in OUR new assessment",
           lambda: client.open_review(OUR_NEW_ASSESSMENT, "Bowtie load"))
must_allow("add a hazard through OUR review",
           lambda: client.add_hazard(OUR_NEW_REVIEW, {"element_name": "x"}))
must_allow("read back OUR new assessment",
           lambda: client.count_hazards(OUR_NEW_ASSESSMENT))
must_allow("upload an import file into OUR new assessment",
           lambda: client.upload_import_file(OUR_NEW_ASSESSMENT, None))
must_allow("upload an import file into OUR review",
           lambda: client.upload_import_file(OUR_NEW_ASSESSMENT, None, review_id=OUR_NEW_REVIEW))
must_refuse("upload an import file into OUR assessment but someone else's review",
            lambda: client.upload_import_file(OUR_NEW_ASSESSMENT, None, review_id=SOMEONE_ELSES_REVIEW), site)
must_refuse("upload an import file into someone else's assessment",
            lambda: client.upload_import_file(SOMEONE_ELSES_ASSESSMENT, None), site)

# --- Even after that, other people's things stay out of reach ------------------
must_refuse("create a second assessment in the same run",
            lambda: client.create_sandbox_assessment("SANDBOX test", "test"), site)
must_refuse("delete OUR OWN assessment (deleting is never allowed)",
            lambda: client.call("DELETE", f"/assessments/{OUR_NEW_ASSESSMENT}"), site)
must_refuse("add a hazard through someone else's review, after creating ours",
            lambda: client.add_hazard(SOMEONE_ELSES_REVIEW, {"element_name": "x"}), site)

# --- If Riskrunner hands back something that is not brand new, stop ------------
for description, reply in (
        ("an assessment that already has hazards in it",
         {"id": OUR_NEW_ASSESSMENT, "name": "SANDBOX test", "parent_id": None, "hazard_links": [{"id": "x"}]}),
        ("an assessment with a parent",
         {"id": OUR_NEW_ASSESSMENT, "name": "SANDBOX test", "parent_id": SOMEONE_ELSES_ASSESSMENT, "hazard_links": []}),
        ("an assessment with a different name",
         {"id": OUR_NEW_ASSESSMENT, "name": "Live register", "parent_id": None, "hazard_links": []})):
    other_site = PretendRiskrunner(assessment_reply=reply)
    other_client = SafeRiskrunner(send=other_site.send)
    try:
        other_client.create_sandbox_assessment("SANDBOX test", "test")
        ok = False
    except SafetyError:
        # the ID must NOT have become usable
        ok = OUR_NEW_ASSESSMENT not in other_client.my_ids
    results.append(ok)
    print(f'{"PASS" if ok else "FAIL"}  refused to trust: {description}')

try:
    SafeRiskrunner(api_address="http://riskrunner.app/api")
    ok = False
except SafetyError:
    ok = True
results.append(ok)
print(f'{"PASS" if ok else "FAIL"}  refused: an address that is not https')

# --- A full rehearsal of the real loading steps against the pretend website ----
from bowtie.loader import run_load

rehearsal_site = PretendRiskrunner()
rehearsal_client = SafeRiskrunner(send=rehearsal_site.send)
run_load(rehearsal_client, [{"element_name": "Hazard A", "top_events": []},
                            {"element_name": "Hazard B", "top_events": []}],
         "someone@example.com", "not-a-real-password", say=lambda text: None)
expected = [("GET", "/health"), ("POST", "/token"), ("GET", "/users/me/context"), ("POST", "/assessments"),
            ("POST", f"/assessments/{OUR_NEW_ASSESSMENT}/reviews"),
            ("POST", f"/reviews/{OUR_NEW_REVIEW}/links/hazards/"),
            ("POST", f"/reviews/{OUR_NEW_REVIEW}/links/hazards/"),
            ("GET", f"/assessments/{OUR_NEW_ASSESSMENT}/links/hazards")]
ok = rehearsal_site.received == expected
results.append(ok)
print(f'{"PASS" if ok else "FAIL"}  rehearsal (messages): a full load sends exactly the eight expected messages, in order')

import_site = PretendRiskrunner()
import_client = SafeRiskrunner(send=import_site.send)
run_load(import_client, [{"element_name": "Hazard A", "top_events": []}],
         "someone@example.com", "not-a-real-password", method="import",
         say=lambda text: None, pause=lambda seconds: None)
expected = [("GET", "/health"), ("POST", "/token"), ("GET", "/users/me/context"), ("POST", "/assessments"),
            ("POST", f"/assessments/{OUR_NEW_ASSESSMENT}/import"),
            ("GET", f"/assessments/{OUR_NEW_ASSESSMENT}/links/hazards")]
ok = import_site.received == expected
results.append(ok)
print(f'{"PASS" if ok else "FAIL"}  rehearsal (import): a full load sends exactly the six expected messages, in order')

secrets_in_log = any("not-a-real-password" in str(entry) or "pretend-token" in str(entry)
                     for entry in rehearsal_client.log)
results.append(not secrets_in_log)
print(f'{"PASS" if not secrets_in_log else "FAIL"}  the log holds no password and no token')

from pathlib import Path
Path("bowtie_output/riskrunner_import_sent.xlsx").unlink(missing_ok=True)   # tidy up the rehearsal's file

print(f"\n{sum(results)} of {len(results)} safety tests passed.")
sys.exit(0 if all(results) else 1)
