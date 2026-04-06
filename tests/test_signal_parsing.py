from types import SimpleNamespace

from november_whiskey.hubspot.form_submitter import extract_submission_data, submit_contact_form
from november_whiskey.utils.validation import normalize_email


def test_extract_submission_data_minimal():
    payload = extract_submission_data({"email": "a@example.com", "openCount": 4})
    assert payload["fields"][0]["name"] == "email"
    assert any(f["name"] == "opencount" for f in payload["fields"])


def test_normalize_email():
    assert normalize_email(" Foo@Example.COM ") == "foo@example.com"


def test_submit_contact_form_syncs_contact_properties():
    calls: list[tuple[str, str, dict]] = []

    class FakeSession:
        def post(self, endpoint, json, timeout):
            _ = (endpoint, json, timeout)
            return SimpleNamespace(ok=True, status_code=200)

    class FakeClient:
        def __init__(self):
            self.timeout = 30
            self.session = FakeSession()

        def request(self, method, path, *, params=None, json_body=None):
            _ = params
            calls.append((method, path, json_body or {}))
            if method == "POST" and path == "/crm/v3/objects/contacts/search":
                return {"results": [{"id": "123"}]}
            if method == "PATCH" and path == "/crm/v3/objects/contacts/123":
                return {"id": "123"}
            raise AssertionError("unexpected request")

    config = SimpleNamespace(portal_id="1", form_id="2")
    event = {
        "email": "john@example.com",
        "pci_datetime": "2026-04-14T13:00:00",
        "teams_join_url": "https://teams.microsoft.com/l/meetup-join/test",
    }
    result = submit_contact_form(FakeClient(), config, event, dry_run=False)

    assert result["submitted"] is True
    assert result["properties_updated"] is True
    assert calls[0][0] == "POST"
    assert calls[0][1] == "/crm/v3/objects/contacts/search"
    assert calls[1][0] == "PATCH"
    assert calls[1][1] == "/crm/v3/objects/contacts/123"
    assert calls[1][2]["properties"]["pci_datetime"] == "2026-04-14T13:00:00"
    assert calls[1][2]["properties"]["teams_join_url"] == "https://teams.microsoft.com/l/meetup-join/test"
