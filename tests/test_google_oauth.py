from types import SimpleNamespace
from time import monotonic

import pytest

from app import google_oauth


class FakeCredentials:
    def __init__(self):
        self.valid = True
        self.expired = False
        self.refresh_token = "refresh-token"
        self.token = "access-token"

    def refresh(self, request):
        self.valid = True
        self.expired = False
        self.token = "refreshed-access-token"


class FakeFlow:
    credentials = FakeCredentials()

    @classmethod
    def from_client_config(cls, client_config, scopes):
        assert client_config["web"]["client_id"] == "client-id"
        assert scopes == ["https://www.googleapis.com/auth/gmail.readonly"]
        return cls()

    def authorization_url(self, **kwargs):
        assert kwargs["access_type"] == "offline"
        assert kwargs["prompt"] == "consent"
        return "https://accounts.google.com/authorize", "test-state"

    def fetch_token(self, authorization_response):
        assert authorization_response.endswith("code=authorization-code")


@pytest.fixture
def configured_google_oauth(monkeypatch):
    credentials = FakeCredentials()
    FakeFlow.credentials = credentials
    monkeypatch.setattr(google_oauth, "Flow", FakeFlow)
    monkeypatch.setattr(google_oauth, "_pending_flows", {})
    monkeypatch.setattr(google_oauth, "_credentials_by_email", {})
    settings = SimpleNamespace(
        google_client_id="client-id",
        google_client_secret="client-secret",
    )
    return settings, credentials


def test_google_oauth_authorization_and_refresh(configured_google_oauth, monkeypatch):
    settings, credentials = configured_google_oauth
    authorization_url, state = google_oauth.create_auth_flow(
        settings,
        "https://example.test/auth/google/callback",
    )
    assert authorization_url == "https://accounts.google.com/authorize"
    assert state == "test-state"

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"emailAddress": "recruiter@gmail.com"}

    class FakeAuthorizedSession:
        def __init__(self, _credentials):
            assert _credentials is credentials

        def get(self, url, timeout):
            assert url == "https://gmail.googleapis.com/gmail/v1/users/me/profile"
            assert timeout == 15
            return FakeResponse()

    monkeypatch.setattr(google_oauth, "AuthorizedSession", FakeAuthorizedSession)
    account = google_oauth.complete_auth_flow(
        settings,
        state,
        "https://example.test/auth/google/callback?state=test-state&code=authorization-code",
    )
    assert account == "recruiter@gmail.com"
    assert google_oauth.get_connected_account(account) == account
    assert google_oauth.acquire_access_token(account) == "access-token"

    credentials.valid = False
    credentials.expired = True
    assert google_oauth.acquire_access_token(account) == "refreshed-access-token"

    google_oauth.disconnect_account(account)
    assert google_oauth.get_connected_account(account) is None


def test_google_oauth_rejects_replayed_state(configured_google_oauth):
    settings, _ = configured_google_oauth

    with pytest.raises(google_oauth.GoogleOAuthError, match="expired") as error:
        google_oauth.complete_auth_flow(
            settings,
            "unknown-state",
            "https://example.test/auth/google/callback?state=unknown-state&code=code",
        )
    assert error.value.code == "flow_expired"


def test_google_oauth_rejects_missing_client_configuration():
    settings = SimpleNamespace(google_client_id="", google_client_secret="")

    with pytest.raises(google_oauth.GoogleOAuthError, match="not configured"):
        google_oauth.create_auth_flow(settings, "https://example.test/callback")


def test_google_oauth_reports_scope_mismatch_safely(configured_google_oauth, monkeypatch):
    settings, _ = configured_google_oauth

    def reject_scope(authorization_response):
        raise Warning("private scope data")

    google_oauth._pending_flows["test-state"] = (
        SimpleNamespace(fetch_token=reject_scope),
        monotonic(),
    )

    with pytest.raises(
        google_oauth.GoogleOAuthError,
        match="different permission scope",
    ) as error:
        google_oauth.complete_auth_flow(
            settings,
            "test-state",
            "https://example.test/callback?code=private-authorization-code",
        )

    assert error.value.code == "scope_mismatch"
    assert "private scope data" not in str(error.value)
    assert "private-authorization-code" not in str(error.value)
