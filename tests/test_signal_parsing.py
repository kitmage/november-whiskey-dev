from types import SimpleNamespace

from november_whiskey.hubspot.form_submitter import extract_submission_data, submit_contact_form
from november_whiskey.utils.validation import normalize_email


def test_extract_submission_data_minimal():
    payload = extract_submission_data({"email": "a@example.com", "pci_datetime": "2026-04-14T13:00:00"})
    assert payload["fields"][0]["name"] == "email"
    assert any(f["name"] == "pci_datetime" for f in payload["fields"])


def test_normalize_email():
    assert normalize_email(" Foo@Example.COM ") == "foo@example.com"


def test_submit_contact_form_submits_fields_without_contact_patch():
    class FakeSession:
        def post(self, endpoint, json, timeout):
            _ = (endpoint, json, timeout)
            return SimpleNamespace(ok=True, status_code=200)

    class FakeClient:
        def __init__(self):
            self.timeout = 30
            self.session = FakeSession()

        def request(self, method, path, *, params=None, json_body=None):
            raise AssertionError(f"unexpected request: {method} {path} {params} {json_body}")

    config = SimpleNamespace(portal_id="1", form_id="2")
    event = {
        "email": "john@example.com",
        "pci_datetime": "2026-04-14T13:00:00",
        "teams_join_url": "https://teams.microsoft.com/l/meetup-join/test",
    }
    result = submit_contact_form(FakeClient(), config, event, dry_run=False)

    assert result["submitted"] is True
    assert result["status"] == 200
