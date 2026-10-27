from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

from app.database import CandidateRepository
from app.email_ingestion import process_email_message
from app.services import CandidateProfile

GMAIL_API_ROOT = "https://gmail.googleapis.com/gmail/v1"
SUPPORTED_RESUME_SUFFIXES = {".pdf", ".docx", ".txt", ".md", ".csv"}


class GmailMailboxError(Exception):
    pass


class GmailMailboxClient:
    def __init__(
        self,
        access_token: str,
        http_get_fn: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
    ) -> None:
        self.access_token = access_token
        self.http_get_fn = http_get_fn or self._default_http_get

    def _default_http_get(self, path: str, headers: dict[str, str]) -> dict[str, Any]:
        url = f"{GMAIL_API_ROOT}{path}"
        parsed_url = urlsplit(url)
        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname != "gmail.googleapis.com"
        ):
            raise GmailMailboxError("Gmail API requests must use Google's HTTPS endpoint.")
        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=30) as response:  # nosec B310 - validated fixed Google HTTPS host.
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise GmailMailboxError(
                f"Gmail API request failed with HTTP {exc.code}. Check Gmail API access and consent."
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise GmailMailboxError("Could not reach the Gmail API. Try again.") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GmailMailboxError("Gmail returned an invalid response.") from exc

    def fetch_unread_messages(self, top: int = 10) -> list[dict[str, Any]]:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }
        query = urlencode({"q": "in:inbox is:unread", "maxResults": str(top)})
        response = self.http_get_fn(f"/users/me/messages?{query}", headers)
        messages = response.get("messages", [])
        enriched_messages: list[dict[str, Any]] = []
        for item in messages:
            message_id = item.get("id")
            if not isinstance(message_id, str) or not message_id:
                continue
            encoded_id = quote(message_id, safe="")
            message = self.http_get_fn(
                f"/users/me/messages/{encoded_id}?format=full",
                headers,
            )
            enriched_messages.append(self._to_email_message(message, headers))
        return enriched_messages

    def _to_email_message(
        self,
        message: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        payload = message.get("payload") or {}
        message_headers = {
            str(item.get("name", "")).lower(): str(item.get("value", ""))
            for item in payload.get("headers", [])
        }
        attachments: list[dict[str, str]] = []
        self._collect_attachments(payload, message.get("id", ""), headers, attachments)
        body = self._extract_plain_body(payload)
        return {
            "id": f"gmail-{message.get('id', 'unknown')}",
            "subject": message_headers.get("subject", ""),
            "from": self._parse_sender(message_headers.get("from", "")),
            "body": {"content": body},
            "attachments": attachments,
        }

    def _collect_attachments(
        self,
        part: dict[str, Any],
        message_id: str,
        headers: dict[str, str],
        attachments: list[dict[str, str]],
    ) -> None:
        filename = str(part.get("filename", ""))
        suffix = Path(filename).suffix.lower()
        if filename and suffix in SUPPORTED_RESUME_SUFFIXES:
            body = part.get("body") or {}
            attachment_id = body.get("attachmentId")
            encoded_data = body.get("data")
            if attachment_id:
                attachment_path = (
                    f"/users/me/messages/{quote(message_id, safe='')}/attachments/"
                    f"{quote(str(attachment_id), safe='')}"
                )
                attachment_response = self.http_get_fn(attachment_path, headers)
                encoded_data = attachment_response.get("data", encoded_data)
            if encoded_data:
                try:
                    decoded = base64.urlsafe_b64decode(
                        str(encoded_data) + "=" * (-len(str(encoded_data)) % 4)
                    )
                except (ValueError, TypeError) as exc:
                    raise GmailMailboxError("Gmail returned an invalid attachment.") from exc
                attachments.append(
                    {
                        "name": filename,
                        "contentType": str(part.get("mimeType", "application/octet-stream")),
                        "contentBytes": base64.b64encode(decoded).decode("ascii"),
                    }
                )
        for child in part.get("parts", []):
            self._collect_attachments(child, message_id, headers, attachments)

    def _extract_plain_body(self, part: dict[str, Any]) -> str:
        if part.get("mimeType") == "text/plain":
            data = (part.get("body") or {}).get("data", "")
            if data:
                try:
                    return base64.urlsafe_b64decode(
                        str(data) + "=" * (-len(str(data)) % 4)
                    ).decode("utf-8", errors="replace")
                except (ValueError, TypeError):
                    return ""
        for child in part.get("parts", []):
            body = self._extract_plain_body(child)
            if body:
                return body
        return ""

    def _parse_sender(self, value: str) -> dict[str, dict[str, str]]:
        display_name, separator, address = value.rpartition("<")
        if separator and address.endswith(">"):
            return {
                "emailAddress": {
                    "name": display_name.strip().strip('"'),
                    "address": address[:-1].strip(),
                }
            }
        return {"emailAddress": {"name": "", "address": value.strip()}}


def ingest_gmail_candidates(
    client: GmailMailboxClient,
    repository: CandidateRepository,
    top: int = 10,
) -> dict[str, int]:
    messages = client.fetch_unread_messages(top=top)
    stored = 0
    skipped = 0
    for message in messages:
        candidate: CandidateProfile = process_email_message(message)
        if not candidate.resume_text.strip() or not message.get("attachments"):
            skipped += 1
            continue
        repository.save_candidate(candidate)
        stored += 1
    return {
        "messages_received": len(messages),
        "candidates_stored": stored,
        "messages_skipped": skipped,
    }
