from types import SimpleNamespace

from november_whiskey.hubspot.signal_finder import find_signal_contacts


def test_find_signal_contacts_thresholding_dedupes_and_pci_filters():
    class FakeClient:
        def request(self, method, path, *, params=None, json_body=None):
            if method == "GET" and path == "/marketing/v3/campaigns/campaign-1/assets/MARKETING_EMAIL":
                return {"results": [{"id": "email-1"}, {"id": "email-2"}]}
            if method == "GET" and path == "/marketing/v3/emails/email-1":
                return {"allEmailCampaignIds": ["ec-1"]}
            if method == "GET" and path == "/marketing/v3/emails/email-2":
                return {"allEmailCampaignIds": ["ec-2"]}
            if method == "GET" and path == "/email/public/v1/events":
                if params["emailCampaignId"] == "ec-1":
                    return {
                        "events": [
                            # split@example.com opens split across two emails; no single email meets threshold.
                            {"id": "split-1", "created": 9999999999999, "recipient": "split@example.com"},
                            {"id": "split-2", "created": 9999999999998, "recipient": "split@example.com"},
                            # include@example.com reaches threshold from this one email.
                            {"id": "inc-1", "created": 9999999999997, "recipient": "include@example.com"},
                            {"id": "inc-2", "created": 9999999999996, "recipient": "include@example.com"},
                            {"id": "inc-3", "created": 9999999999995, "recipient": "include@example.com"},
                            # duplicate@example.com has duplicated open rows (same campaign/timestamp/send metadata).
                            {
                                "created": 9999999999994,
                                "recipient": "duplicate@example.com",
                                "sendId": "send-1",
                                "filteredEvent": False,
                                "userAgent": "UA-1",
                            },
                            {
                                "created": 9999999999994,
                                "recipient": "duplicate@example.com",
                                "sendId": "send-1",
                                "filteredEvent": False,
                                "userAgent": "UA-1",
                            },
                            {
                                "created": 9999999999993,
                                "recipient": "duplicate@example.com",
                                "sendId": "send-2",
                                "filteredEvent": False,
                                "userAgent": "UA-1",
                            },
                            {
                                "created": 9999999999993,
                                "recipient": "duplicate@example.com",
                                "sendId": "send-2",
                                "filteredEvent": False,
                                "userAgent": "UA-1",
                            },
                        ],
                        "hasMore": False,
                    }
                if params["emailCampaignId"] == "ec-2":
                    return {
                        "events": [
                            {"id": "split-3", "created": 9999999999992, "recipient": "split@example.com"},
                            # Completed contact reaches threshold but should still be excluded by pci status.
                            {"id": "done-1", "created": 9999999999991, "recipient": "completed@example.com"},
                            {"id": "done-2", "created": 9999999999990, "recipient": "completed@example.com"},
                            {"id": "done-3", "created": 9999999999989, "recipient": "completed@example.com"},
                        ],
                        "hasMore": False,
                    }
            if method == "GET" and path == "/crm/v3/lists/list-1/memberships":
                return {
                    "results": [
                        {"recordId": "1"},
                        {"recordId": "2"},
                        {"recordId": "3"},
                        {"recordId": "4"},
                    ]
                }
            if method == "POST" and path == "/crm/v3/objects/contacts/batch/read":
                _ = json_body
                return {
                    "results": [
                        {
                            "id": "1",
                            "properties": {
                                "email": "split@example.com",
                                "pci_automation": "pci_started",
                                "firstname": "Split",
                                "lastname": "Person",
                            },
                        },
                        {
                            "id": "2",
                            "properties": {
                                "email": "include@example.com",
                                "pci_automation": "pci_started",
                                "firstname": "Include",
                                "lastname": "Person",
                            },
                        },
                        {
                            "id": "3",
                            "properties": {
                                "email": "duplicate@example.com",
                                "pci_automation": "pci_started",
                                "firstname": "Duplicate",
                                "lastname": "Person",
                            },
                        },
                        {
                            "id": "4",
                            "properties": {
                                "email": "completed@example.com",
                                "pci_automation": "pci_completed",
                                "firstname": "Done",
                                "lastname": "Person",
                            },
                        },
                    ]
                }
            raise AssertionError(f"Unexpected request: {method} {path} {params} {json_body}")

    config = SimpleNamespace(
        campaign_id="campaign-1",
        list_id="list-1",
        lookback_window_hours=24,
        signal_threshold=3,
        app_id=2286,
        property_name="pci_automation",
    )

    contacts = find_signal_contacts(FakeClient(), config)
    by_email = {contact.email: contact for contact in contacts}

    # split@example.com has 2 opens in ec-1 and 1 open in ec-2 (3 total), but max single-email opens is 2.
    assert "split@example.com" not in by_email

    # include@example.com has 3 opens in ec-1 and should be included.
    assert by_email["include@example.com"].openCount == 3

    # duplicate@example.com should dedupe to 2 unique opens and stay below threshold 3.
    assert "duplicate@example.com" not in by_email

    # Existing PCI behavior remains unchanged.
    assert "completed@example.com" not in by_email
