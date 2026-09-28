from __future__ import annotations

import json
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from typing import Any, Callable, Dict, List

from app.email_ingestion import process_email_message
from app.database import CandidateRepository
from app.services import CandidateProfile


class GraphMailboxClient:
    def __init__(self, access_token: str, http_get_fn: Callable[[str, Dict[str, str]], Dict[str, Any]] | None = None):
        self.access_token = access_token
        self.http_get_fn = http_get_fn or self._default_http_get

    def _default_http_get(self, path: str, headers: Dict[str, str]) -> Dict[str, Any]:
        url = f"https://graph.microsoft.com/v1.0{path}"
        if urlsplit(url).scheme != "https":
            raise ValueError("Microsoft Graph requests must use HTTPS.")

        request = Request(
            url,
            headers=headers,
            method="GET",
        )
        with urlopen(request, timeout=30) as response:  # nosec B310 - URL is fixed to Microsoft Graph HTTPS.
            return json.loads(response.read().decode("utf-8"))

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


def ingest_mailbox_candidates(
    client: GraphMailboxClient,
    repository: CandidateRepository,
    mailbox_address: str,
    top: int = 10,
) -> Dict[str, int]:
    messages = client.fetch_enriched_messages(mailbox_address, top=top)
    candidates = extract_candidates_from_messages(messages)
    stored = 0
    skipped = 0

    for candidate in candidates:
        if not candidate.resume_text.strip():
            skipped += 1
            continue
        repository.save_candidate(candidate)
        stored += 1

    return {
        "messages_received": len(messages),
        "candidates_stored": stored,
        "messages_skipped": skipped,
    }
