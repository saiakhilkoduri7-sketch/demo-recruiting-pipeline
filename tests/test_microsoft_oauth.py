from types import SimpleNamespace

import pytest

from app import microsoft_oauth


class FakeMicrosoftClient:
    def __init__(self):
        self.removed_accounts = []

    def initiate_auth_code_flow(self, scopes, redirect_uri, prompt):
        assert scopes == ["User.Read", "Mail.Read"]
        assert redirect_uri == "https://example.test/auth/microsoft/callback"
        assert prompt == "select_account"
        return {"state": "test-state", "auth_uri": "https://login.microsoftonline.com/authorize"}

    def acquire_token_by_auth_code_flow(self, flow, auth_response):
        assert flow["state"] == "test-state"
        assert auth_response["state"] == "test-state"
        return {
            "id_token_claims": {"preferred_username": "recruiter@outlook.com"},
            "account": {"username": "recruiter@outlook.com"},
        }

    def get_accounts(self, username=None):
        if username and username != "recruiter@outlook.com":
            return []
        return [{"username": "recruiter@outlook.com"}]

    def acquire_token_silent(self, scopes, account):
        assert scopes == ["User.Read", "Mail.Read"]
        assert account["username"] == "recruiter@outlook.com"
        return {"access_token": "server-side-access-token"}

    def remove_account(self, account):
        self.removed_accounts.append(account)


@pytest.fixture
def configured_microsoft_client(monkeypatch):
    client = FakeMicrosoftClient()
    monkeypatch.setattr(microsoft_oauth, "_client", client)
    monkeypatch.setattr(
        microsoft_oauth,
        "_client_credentials",
        ("client-id", "client-secret"),
    )
    monkeypatch.setattr(microsoft_oauth, "_pending_flows", {})
    settings = SimpleNamespace(
        microsoft_client_id="client-id",
        microsoft_client_secret="client-secret",
    )
    return settings, client


def test_microsoft_oauth_flow_keeps_credentials_server_side(configured_microsoft_client):
    settings, client = configured_microsoft_client
    flow = microsoft_oauth.create_auth_flow(
        settings,
        "https://example.test/auth/microsoft/callback",
    )

    assert flow["auth_uri"].startswith("https://login.microsoftonline.com/")
    assert microsoft_oauth.complete_auth_flow(
        settings,
        "test-state",
        {"state": "test-state", "code": "authorization-code"},
    ) == "recruiter@outlook.com"
    assert microsoft_oauth.acquire_access_token(
        settings,
        "recruiter@outlook.com",
    ) == "server-side-access-token"
    assert microsoft_oauth.get_connected_account(
        settings,
        "recruiter@outlook.com",
    ) == "recruiter@outlook.com"

    microsoft_oauth.disconnect_account(settings, "recruiter@outlook.com")
    assert client.removed_accounts == [{"username": "recruiter@outlook.com"}]


def test_microsoft_oauth_rejects_replayed_or_missing_state(configured_microsoft_client):
    settings, _ = configured_microsoft_client

    with pytest.raises(microsoft_oauth.MicrosoftOAuthError, match="expired"):
        microsoft_oauth.complete_auth_flow(
            settings,
            "missing-state",
            {"state": "missing-state", "code": "authorization-code"},
        )


def test_microsoft_oauth_requires_cached_account(configured_microsoft_client):
    settings, _ = configured_microsoft_client

    with pytest.raises(microsoft_oauth.MicrosoftAccountNotConnected, match="Connect"):
        microsoft_oauth.acquire_access_token(settings, None)
