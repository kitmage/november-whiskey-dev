from __future__ import annotations

from november_whiskey.hubspot.signal_finder import HubSpotClient


def test_hubspot_client_ignores_403_on_contact_patch(monkeypatch):
    class FakeResponse:
        ok = False
        status_code = 403

        def json(self):
            return {}

    class FakeSession:
        def __init__(self):
            self.headers = {}

        def request(self, method, url, params=None, json=None, timeout=None):
            _ = (method, url, params, json, timeout)
            return FakeResponse()

    import requests

    monkeypatch.setattr(requests, "Session", FakeSession)
    client = HubSpotClient("token")
    result = client.request("PATCH", "/crm/v3/objects/contacts/123", json_body={"properties": {"x": "y"}})
    assert result["ignored"] is True
    assert result["status"] == 403
