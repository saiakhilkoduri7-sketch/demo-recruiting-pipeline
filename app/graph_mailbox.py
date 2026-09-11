from __future__ import annotations

from typing import Any, Callable, Dict, List

from app.email_ingestion import process_email_message
from app.services import CandidateProfile


class GraphMailboxClient:
    def __init__(self, access_token: str, http_get_fn: Callable[[str, Dict[str, str]], Dict[str, Any]] | None = None):
        self.access_token = access_token
        self.http_get_fn = http_get_fn or self._default_http_get

    def _default_http_get(self, path: str, headers: Dict[str, str]) -> Dict[str, Any]:
        raise NotImplementedError("Provide http_get_fn to use GraphMailboxClient in tests or a mock environment.")

    def fetch_enriched_messages(self, mailbox_address: str, top: int = 10) -> List[Dict[str, Any]]:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        messages_path = f"/users/{mailbox_address}/messages?$top={top}&$filter=isRead eq false"
        messages_response = self.http_get_fn(messages_path, headers)
        messages = messages_response.get("value", [])

        enriched_messages: List[Dict[str, Any]] = []
        for message in messages:
            message_id = message.get("id")
            if not message_id:
                continue

            message_path = f"/users/{mailbox_address}/messages/{message_id}"
            enriched_message = self.http_get_fn(message_path, headers)

            attachments_path = f"/users/{mailbox_address}/messages/{message_id}/attachments"
            attachments_response = self.http_get_fn(attachments_path, headers)
            enriched_message["attachments"] = attachments_response.get("value", [])
            enriched_messages.append(enriched_message)

        return enriched_messages


def extract_candidates_from_messages(messages: List[Dict[str, Any]]) -> List[CandidateProfile]:
    return [process_email_message(message) for message in messages]
