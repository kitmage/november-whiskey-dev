from types import SimpleNamespace

from november_whiskey.hubspot.signal_finder import find_signal_contacts


def test_find_signal_contacts_keeps_pci_started_but_excludes_pci_completed():
    class FakeClient:
        def request(self, method, path, *, params=None, json_body=None):
            if method == "GET" and path == "/marketing/v3/campaigns/campaign-1/assets/MARKETING_EMAIL":
                return {"results": [{"id": "email-1"}]}
            if method == "GET" and path == "/marketing/v3/emails/email-1":
                return {"allEmailCampaignIds": ["ec-1"]}
            if method == "GET" and path == "/email/public/v1/events":
                assert params is not None
                assert params["eventType"] == "OPEN"
                assert params["excludeFilteredEvents"] == "true"
                return {
                    "events": [
                        {"created": 9999999999999, "recipient": "started@example.com"},
                        {"created": 9999999999999, "recipient": "completed@example.com"},
                    ],
                    "hasMore": False,
                }
            if method == "GET" and path == "/crm/v3/lists/list-1/memberships":
                return {"results": [{"recordId": "1"}, {"recordId": "2"}]}
            if method == "POST" and path == "/crm/v3/objects/contacts/batch/read":
                _ = json_body
                return {
                    "results": [
                        {
                            "id": "1",
                            "properties": {
                                "email": "started@example.com",
                                "pci_automation": "pci_started",
                                "firstname": "Start",
                                "lastname": "Ed",
                            },
                        },
                        {
                            "id": "2",
                            "properties": {
                                "email": "completed@example.com",
                                "pci_automation": "pci_completed",
                                "firstname": "Done",
                                "lastname": "Ed",
                            },
                        },
                    ]
                }
            raise AssertionError(f"Unexpected request: {method} {path} {params} {json_body}")

    config = SimpleNamespace(
        campaign_id="campaign-1",
        list_id="list-1",
        lookback_window_hours=24,
        signal_threshold=1,
        app_id=2286,
        property_name="pci_automation",
    )

    contacts = find_signal_contacts(FakeClient(), config)
    assert [c.email for c in contacts] == ["started@example.com"]


def test_find_signal_contacts_uses_max_opens_on_single_email_campaign():
    class FakeClient:
        def request(self, method, path, *, params=None, json_body=None):
            if method == "GET" and path == "/marketing/v3/campaigns/campaign-1/assets/MARKETING_EMAIL":
                return {"results": [{"id": "email-1"}]}
            if method == "GET" and path == "/marketing/v3/emails/email-1":
                return {"allEmailCampaignIds": ["ec-1", "ec-2"]}
            if method == "GET" and path == "/email/public/v1/events":
                assert params is not None
                if params["emailCampaignId"] == "ec-1":
                    return {
                        "events": [
                            {"created": 9999999999999, "recipient": "started@example.com"},
                            {"created": 9999999999998, "recipient": "started@example.com"},
                        ],
                        "hasMore": False,
                    }
                if params["emailCampaignId"] == "ec-2":
                    return {
                        "events": [
                            {"created": 9999999999997, "recipient": "started@example.com"},
                        ],
                        "hasMore": False,
                    }
                raise AssertionError(f"unexpected emailCampaignId: {params['emailCampaignId']}")
            if method == "GET" and path == "/crm/v3/lists/list-1/memberships":
                return {"results": [{"recordId": "1"}]}
            if method == "POST" and path == "/crm/v3/objects/contacts/batch/read":
                _ = json_body
                return {
                    "results": [
                        {
                            "id": "1",
                            "properties": {
                                "email": "started@example.com",
                                "pci_automation": "pci_started",
                                "firstname": "Start",
                                "lastname": "Ed",
                            },
                        }
                    ]
                }
            raise AssertionError(f"Unexpected request: {method} {path} {params} {json_body}")

    config = SimpleNamespace(
        campaign_id="campaign-1",
        list_id="list-1",
        lookback_window_hours=24,
        signal_threshold=2,
        app_id=2286,
        property_name="pci_automation",
    )

    contacts = find_signal_contacts(FakeClient(), config)
    assert len(contacts) == 1
    assert contacts[0].email == "started@example.com"
    assert contacts[0].openCount == 2
