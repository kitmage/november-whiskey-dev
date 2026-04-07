from __future__ import annotations

from november_whiskey.utils.notifications import send_discord_webhook


def test_send_discord_webhook_uses_custom_user_agent(monkeypatch):
    captured = {}

    class FakeResponse:
        ok = True

    def fake_post(url, headers=None, data=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["data"] = data
        captured["timeout"] = timeout
        return FakeResponse()

    import requests

    monkeypatch.setattr(requests, "post", fake_post)
    assert send_discord_webhook("https://discord.example/webhook", "hello", timeout_seconds=3.0) is True
    assert captured["url"] == "https://discord.example/webhook"
    assert "november-whiskey/1.0" in captured["headers"]["User-Agent"]
    assert captured["headers"]["Content-Type"] == "application/json"
