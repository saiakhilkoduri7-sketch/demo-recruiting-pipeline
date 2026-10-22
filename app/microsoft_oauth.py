from __future__ import annotations

from threading import RLock
from time import monotonic
from typing import Any

import msal

from app.config import Settings

SCOPES = ["User.Read", "Mail.Read"]
AUTHORITY = "https://login.microsoftonline.com/common"
FLOW_TTL_SECONDS = 600
MAX_PENDING_FLOWS = 20


class MicrosoftOAuthError(Exception):
    pass


class MicrosoftAccountNotConnected(MicrosoftOAuthError):
    pass


_lock = RLock()
_client: msal.ConfidentialClientApplication | None = None
_client_credentials: tuple[str, str] | None = None
_pending_flows: dict[str, tuple[dict[str, Any], float]] = {}


def _get_client(settings: Settings) -> msal.ConfidentialClientApplication:
    global _client, _client_credentials

    if not settings.microsoft_client_id or not settings.microsoft_client_secret:
        raise MicrosoftOAuthError("Microsoft sign-in is not configured.")

    credentials = (settings.microsoft_client_id, settings.microsoft_client_secret)
    with _lock:
        if credentials != _client_credentials:
            _client = msal.ConfidentialClientApplication(
                client_id=credentials[0],
                authority=AUTHORITY,
                client_credential=credentials[1],
            )
            _client_credentials = credentials
            _pending_flows.clear()
        if _client is None:
            raise MicrosoftOAuthError("Microsoft sign-in is not configured.")
        return _client


def create_auth_flow(settings: Settings, redirect_uri: str) -> dict[str, Any]:
    with _lock:
        client = _get_client(settings)
        flow = client.initiate_auth_code_flow(
            scopes=SCOPES,
            redirect_uri=redirect_uri,
            prompt="select_account",
        )
    state = flow.get("state")
    auth_uri = flow.get("auth_uri")
    if not state or not auth_uri:
        raise MicrosoftOAuthError("Microsoft could not start sign-in.")

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

    return flow


def discard_auth_flow(state: str) -> None:
    with _lock:
        _pending_flows.pop(state, None)


def complete_auth_flow(
    settings: Settings, state: str, auth_response: dict[str, str]
) -> str:
    with _lock:
        pending = _pending_flows.pop(state, None)
    if pending is None or monotonic() - pending[1] > FLOW_TTL_SECONDS:
        raise MicrosoftOAuthError("Microsoft sign-in expired. Please try again.")

    with _lock:
        result = _get_client(settings).acquire_token_by_auth_code_flow(
            pending[0],
            auth_response,
        )
    if result.get("error"):
        raise MicrosoftOAuthError("Microsoft sign-in failed. Please try again.")

    claims = result.get("id_token_claims") or {}
    account = result.get("account") or {}
    username = claims.get("preferred_username") or account.get("username")
    if not username:
        raise MicrosoftOAuthError("Microsoft did not return an account identifier.")
    return str(username)


def get_connected_account(settings: Settings, username: str | None) -> str | None:
    if not username:
        return None
    with _lock:
        client = _get_client(settings)
        matching_accounts = client.get_accounts(username=username)
    if not matching_accounts:
        return None
    return str(matching_accounts[0].get("username") or username)


def acquire_access_token(settings: Settings, username: str | None) -> str:
    if not username:
        raise MicrosoftAccountNotConnected("Connect a Microsoft account first.")

    with _lock:
        client = _get_client(settings)
        accounts = client.get_accounts(username=username)
        if not accounts:
            raise MicrosoftAccountNotConnected("Reconnect your Microsoft account to continue.")
        result = client.acquire_token_silent(SCOPES, account=accounts[0])
    if not result or not result.get("access_token"):
        raise MicrosoftAccountNotConnected("Reconnect your Microsoft account to continue.")
    return str(result["access_token"])


def disconnect_account(settings: Settings, username: str | None) -> None:
    if not username:
        return
    with _lock:
        client = _get_client(settings)
        for account in client.get_accounts(username=username):
            client.remove_account(account)
