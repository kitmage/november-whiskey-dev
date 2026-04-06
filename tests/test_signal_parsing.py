from november_whiskey.hubspot.form_submitter import extract_submission_data
from november_whiskey.utils.validation import normalize_email


def test_extract_submission_data_minimal():
    payload = extract_submission_data({"email": "a@example.com", "openCount": 4})
    assert payload["fields"][0]["name"] == "email"
    assert any(f["name"] == "opencount" for f in payload["fields"])


def test_normalize_email():
    assert normalize_email(" Foo@Example.COM ") == "foo@example.com"
