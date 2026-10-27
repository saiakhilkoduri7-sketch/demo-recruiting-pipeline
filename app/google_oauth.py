from __future__ import annotations

from threading import RLock
from time import monotonic

from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from app.config import Settings

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
OPENID_SCOPES = ["openid", "email"]
FLOW_TTL_SECONDS = 600
MAX_PENDING_FLOWS = 20


class GoogleOAuthError(Exception):
    pass


class GoogleAccountNotConnected(GoogleOAuthError):
    pass


_lock = RLock()
_pending_flows: dict[str, tuple[Flow, float]] = {}
_credentials_by_email: dict[str, Credentials] = {}


def _client_config(settings: Settings) -> dict:
    if not settings.google_client_id or not settings.google_client_secret:
        raise GoogleOAuthError("Google sign-in is not configured.")
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def create_auth_flow(settings: Settings, redirect_uri: str) -> tuple[str, str]:
    config = _client_config(settings)
    flow = Flow.from_client_config(config, scopes=[*OPENID_SCOPES, GMAIL_READONLY_SCOPE])
    flow.redirect_uri = redirect_uri
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    with _lock:
        now = monotonic()
        expired_states = [
            flow_state
            for flow_state, (_, created_at) in _pending_flows.items()
            if now - created_at > FLOW_TTL_SECONDS
        ]
        for flow_state in expired_states:
            _pending_flows.pop(flow_state, None)
        if len(_pending_flows) >= MAX_PENDING_FLOWS:
            oldest_state = min(_pending_flows, key=lambda key: _pending_flows[key][1])
            _pending_flows.pop(oldest_state, None)
        _pending_flows[state] = (flow, now)
    return authorization_url, state


def discard_auth_flow(state: str) -> None:
    with _lock:
        _pending_flows.pop(state, None)


def complete_auth_flow(
    settings: Settings,
    state: str,
    authorization_response: str,
) -> str:
    with _lock:
        pending = _pending_flows.pop(state, None)
        if pending is None or monotonic() - pending[1] > FLOW_TTL_SECONDS:
            raise GoogleOAuthError("Google sign-in expired. Please try again.")
        flow = pending[0]
        try:
            flow.fetch_token(authorization_response=authorization_response)
        except Exception as exc:
            raise GoogleOAuthError("Google sign-in failed. Please try again.") from exc
        credentials = flow.credentials

    try:
        response = AuthorizedSession(credentials).get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            timeout=15,
        )
        response.raise_for_status()
        email = response.json().get("email")
    except Exception as exc:
        raise GoogleOAuthError("Could not verify the connected Google account.") from exc
    if not isinstance(email, str) or not email.strip():
        raise GoogleOAuthError("Google did not return an email address.")

    with _lock:
        _credentials_by_email[email.casefold()] = credentials
    return email


def get_connected_account(username: str | None) -> str | None:
    if not username:
        return None
    with _lock:
        credentials = _credentials_by_email.get(username.casefold())
        if credentials:
            return username
    return None


def acquire_access_token(username: str | None) -> str:
    if not username:
        raise GoogleAccountNotConnected("Connect a Google account first.")
    with _lock:
        credentials = _credentials_by_email.get(username.casefold())
        if not credentials:
            raise GoogleAccountNotConnected(
                "Reconnect your Google account to continue."
            )
        try:
            if not credentials.valid:
                if credentials.expired and credentials.refresh_token:
                    credentials.refresh(Request())
                else:
                    raise GoogleAccountNotConnected(
                        "Reconnect your Google account to continue."
                    )
            if not credentials.token:
                raise GoogleAccountNotConnected(
                    "Reconnect your Google account to continue."
                )
            return credentials.token
        except GoogleAccountNotConnected:
            raise
        except Exception as exc:
            raise GoogleAccountNotConnected(
                "Google authorization expired. Reconnect your account."
            ) from exc


def disconnect_account(username: str | None) -> None:
    if username:
        with _lock:
            _credentials_by_email.pop(username.casefold(), None)
