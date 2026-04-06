from __future__ import annotations

from november_whiskey.config import GraphConfig
from november_whiskey.exceptions import GraphAPIError


def get_access_token(config: GraphConfig) -> str:
    import msal

    app = msal.ConfidentialClientApplication(
        client_id=config.client_id,
        authority=f"https://login.microsoftonline.com/{config.tenant_id}",
        client_credential=config.client_secret,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    token = result.get("access_token")
    if not token:
        raise GraphAPIError("Could not acquire Microsoft Graph token")
    return token
