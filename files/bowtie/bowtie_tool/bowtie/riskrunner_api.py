"""
riskrunner_api.py
The ONLY file that talks to Riskrunner. Every message goes through one gate,
SafeRiskrunner.call(), and that gate enforces the safety rules below.

SAFETY RULES (enforced in code, not left to care)
  1. Only the calls in ALLOWED_CALLS can be sent. There is no delete, no merge
     and no general "update" in that list, so the program cannot send one.
  2. Any call that names an assessment or a review must name one that THIS RUN
     created. IDs of existing assessments are refused before anything is sent.
  3. The program never asks for, reads or accepts the ID of an existing
     assessment. The only way an ID becomes usable is by coming back from our
     own "create" call.
  4. One run can create one assessment, and it must come back brand new:
     the name we asked for, no parent, nothing inside it.
  5. Messages only go to the https address in settings.py.
  6. The password and the login token are kept in memory only. They are never
     written to a file or to the log.
"""

import re
from datetime import datetime

from bowtie.settings import RISKRUNNER_API

# What an ID looks like in Riskrunner, e.g. 328e2042-f3fe-44b8-b333-291470e8086b
ID_PATTERN = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

# The complete list of messages this program is able to send.
# "{mine}" stands for an ID that was created during this run.
ALLOWED_CALLS = [
    ("GET",  "/health"),                            # is Riskrunner reachable?
    ("POST", "/token"),                             # log in
    ("GET",  "/users/me/context"),                  # who am I, and may I create assessments?
    ("POST", "/assessments"),                       # create ONE new, empty assessment
    ("POST", "/assessments/{mine}/reviews"),        # open an editing session in MY new assessment
    ("PUT",  "/reviews/{mine}"),                    # switch MY editing session to "active"
    ("POST", "/reviews/{mine}/links/hazards/"),     # add a hazard tree in MY editing session
    ("GET",  "/assessments/{mine}/links/hazards"),  # read back what MY new assessment now holds
    ("POST", "/assessments/{mine}/import"),         # upload an Excel import file into MY new assessment
    ("POST", "/assessments/{mine}/reviews/{mine}/import"),  # the same, inside MY editing session
]


class SafetyError(Exception):
    """Raised when the program itself refuses to send a message."""


class RiskrunnerError(Exception):
    """Raised when Riskrunner answers with an error."""

    def __init__(self, status, reply):
        super().__init__(f"Riskrunner answered {status}: {str(reply)[:500]}")
        self.status = status
        self.reply = reply


def send_with_requests(method, url, headers, json_body, form, params, upload=None):
    """Really send one message over the internet. Returns (status code, reply)."""
    import requests  # imported here so the safety test can run without it installed
    files = None
    if upload:       # upload = path of an Excel file to attach
        files = {"file": (upload.name, upload.read_bytes(),
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    response = requests.request(method, url, headers=headers, json=json_body, data=form,
                                params=params, files=files, timeout=300)
    try:
        reply = response.json()
    except ValueError:
        reply = response.text
    return response.status_code, reply


class SafeRiskrunner:
    def __init__(self, api_address=RISKRUNNER_API, send=send_with_requests):
        if not api_address.startswith("https://"):
            raise SafetyError("Refused: the Riskrunner address must start with https://")
        self.api_address = api_address.rstrip("/")
        self.send = send                   # the function that really sends (swapped for a fake in tests)
        self.token = None                  # filled in by login()
        self.my_ids = set()                # IDs created during this run: the only ones we may use
        self.assessment_requested = False  # becomes True once we have asked for our one assessment
        self.log = []                      # a record of every message, without secrets

    # ------------------------------------------------------------------ gate
    def check_allowed(self, method, path):
        """Raise SafetyError unless this exact kind of message is permitted."""
        if not path.startswith("/") or "?" in path or ".." in path or "//" in path:
            raise SafetyError(f"Refused: odd-looking path {path!r}")
        for found_id in re.findall(ID_PATTERN, path):
            if found_id not in self.my_ids:
                raise SafetyError(f"Refused: {method} {path} names an ID that this run did not create. "
                                  "The program only writes to things it made itself.")
        pattern = re.sub(ID_PATTERN, "{mine}", path)
        if (method, pattern) not in ALLOWED_CALLS:
            raise SafetyError(f"Refused: {method} {pattern} is not in the list of allowed calls.")
        if (method, pattern) == ("POST", "/assessments") and self.assessment_requested:
            raise SafetyError("Refused: this run has already created its one assessment.")
        return pattern

    def call(self, method, path, json_body=None, form=None, params=None, upload=None):
        """The one gate. Check the message, send it, record it, return the reply."""
        pattern = self.check_allowed(method, path)
        if (method, pattern) == ("POST", "/assessments"):
            self.assessment_requested = True

        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        status, reply = self.send(method, self.api_address + path, headers, json_body, form, params, upload)

        entry = {"time": datetime.now().isoformat(timespec="seconds"), "method": method,
                 "path": path, "status": status}
        if status >= 400 and pattern != "/token":
            entry["riskrunner_said"] = str(reply)[:2000]   # helps to diagnose; never holds the password
        self.log.append(entry)

        if status >= 400:
            if pattern == "/token":
                reply = ("login was refused. Check the email and password. "
                         "Accounts that need a two-step code are not supported by this loader yet.")
            raise RiskrunnerError(status, reply)
        return reply

    # ----------------------------------------------------------------- steps
    def is_reachable(self):
        self.call("GET", "/health")
        return True

    def login(self, email, password):
        reply = self.call("POST", "/token",
                          form={"username": email, "password": password, "grant_type": "password"})
        self.token = reply["access_token"]

    def who_am_i(self):
        return self.call("GET", "/users/me/context")

    def create_sandbox_assessment(self, name, description):
        """Create one new assessment and prove it is brand new before trusting its ID."""
        reply = self.call("POST", "/assessments", json_body={"name": name, "description": description})
        new_id = reply.get("id")
        if not new_id or not re.fullmatch(ID_PATTERN, str(new_id)):
            raise SafetyError("Stopped: Riskrunner did not return an ID for the new assessment.")
        if reply.get("name") != name:
            raise SafetyError("Stopped: the assessment that came back does not have the name we asked for.")
        if reply.get("parent_id"):
            raise SafetyError("Stopped: the new assessment has a parent. It must stand alone.")
        if reply.get("hazard_links") or reply.get("hazard_elements"):
            raise SafetyError("Stopped: the new assessment is not empty.")
        self.my_ids.add(new_id)      # from now on, and only now, this ID may be used
        return reply

    def open_review(self, assessment_id, name):
        """Open an editing session ("review") inside our own assessment."""
        body = {"name": name, "type": "entities", "status": "active"}
        path = f"/assessments/{assessment_id}/reviews"
        try:
            reply = self.call("POST", path, json_body=body)
        except RiskrunnerError as error:
            if error.status not in (400, 409, 422):
                raise
            # Some setups may not accept "active" at creation: create it, then switch it on.
            reply = self.call("POST", path, json_body={"name": name, "type": "entities"})
            self._register_review(reply, assessment_id)
            self.call("PUT", f"/reviews/{reply['id']}", json_body={"status": "active"})
            return reply
        self._register_review(reply, assessment_id)
        return reply

    def _register_review(self, reply, assessment_id):
        if reply.get("assessment_id") != assessment_id:
            raise SafetyError("Stopped: the review that came back belongs to a different assessment.")
        self.my_ids.add(reply["id"])

    def add_hazard(self, review_id, hazard_tree):
        """Send one hazard with all its top events, causes, controls and consequences."""
        return self.call("POST", f"/reviews/{review_id}/links/hazards/",
                         json_body={"data": [hazard_tree], "create_missing_elements": True})

    def upload_import_file(self, assessment_id, file_path, review_id=None):
        """Upload an Excel file in Riskrunner's export layout into our own assessment (or our own review)."""
        path = f"/assessments/{assessment_id}/import"
        if review_id:
            path = f"/assessments/{assessment_id}/reviews/{review_id}/import"
        return self.call("POST", path, upload=file_path)

    def count_hazards(self, assessment_id):
        reply = self.call("GET", f"/assessments/{assessment_id}/links/hazards",
                          params={"offset": 0, "limit": 100, "include_draft": "true"})
        return len(reply.get("items", [])) if isinstance(reply, dict) else None
