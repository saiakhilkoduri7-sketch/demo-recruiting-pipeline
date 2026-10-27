import base64
from urllib.parse import parse_qs, urlsplit

from app.database import CandidateRepository
from app.google_mailbox import GmailMailboxClient, ingest_gmail_candidates


def _encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def test_gmail_client_fetches_unread_inbox_and_resume_attachment():
    responses = {
        "/users/me/messages?q=in%3Ainbox+is%3Aunread&maxResults=5": {
            "messages": [{"id": "message-123"}]
        },
        "/users/me/messages/message-123?format=full": {
            "id": "message-123",
            "payload": {
                "mimeType": "multipart/mixed",
                "headers": [
                    {"name": "From", "value": "Alice Applicant <alice@example.com>"},
                    {"name": "Subject", "value": "Application for Engineer"},
                ],
                "parts": [
                    {
                        "filename": "resume.txt",
                        "mimeType": "text/plain",
                        "body": {"data": _encoded(b"Python engineering experience")},
                    }
                ],
            },
        },
    }
    request_headers = []

    def http_get(path, headers):
        request_headers.append(headers)
        return responses[path]

    client = GmailMailboxClient("google-test-token", http_get_fn=http_get)
    messages = client.fetch_unread_messages(top=5)

    assert len(messages) == 1
    assert messages[0]["id"] == "gmail-message-123"
    assert messages[0]["from"]["emailAddress"] == {
        "name": "Alice Applicant",
        "address": "alice@example.com",
    }
    assert messages[0]["attachments"][0]["contentBytes"] == base64.b64encode(
        b"Python engineering experience"
    ).decode("ascii")
    assert parse_qs(urlsplit(next(iter(responses))).query) == {
        "q": ["in:inbox is:unread"],
        "maxResults": ["5"],
    }
    assert request_headers[0]["Authorization"] == "Bearer google-test-token"


def test_gmail_client_fetches_indirect_attachment_data():
    responses = {
        "/users/me/messages?q=in%3Ainbox+is%3Aunread&maxResults=10": {
            "messages": [{"id": "message/with-special"}]
        },
        "/users/me/messages/message%2Fwith-special?format=full": {
            "id": "message/with-special",
            "payload": {
                "headers": [],
                "parts": [
                    {
                        "filename": "resume.pdf",
                        "mimeType": "application/pdf",
                        "body": {"attachmentId": "attachment-1"},
                    }
                ],
            },
        },
        "/users/me/messages/message%2Fwith-special/attachments/attachment-1": {
            "data": _encoded(b"pdf bytes")
        },
    }
    client = GmailMailboxClient("token", http_get_fn=lambda path, headers: responses[path])

    messages = client.fetch_unread_messages()

    assert messages[0]["attachments"][0]["contentBytes"] == base64.b64encode(
        b"pdf bytes"
    ).decode("ascii")


def test_gmail_import_saves_supported_resume_and_skips_email_without_attachment(tmp_path):
    responses = {
        "/users/me/messages?q=in%3Ainbox+is%3Aunread&maxResults=10": {
            "messages": [{"id": "with-resume"}, {"id": "no-resume"}]
        },
        "/users/me/messages/with-resume?format=full": {
            "id": "with-resume",
            "payload": {
                "headers": [{"name": "From", "value": "Applicant <a@example.com>"}],
                "parts": [
                    {
                        "filename": "resume.txt",
                        "mimeType": "text/plain",
                        "body": {"data": _encoded(b"Python FastAPI")},
                    }
                ],
            },
        },
        "/users/me/messages/no-resume?format=full": {
            "id": "no-resume",
            "payload": {
                "headers": [{"name": "From", "value": "Sender <sender@example.com>"}],
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": _encoded(b"Hello there")}}
                ],
            },
        },
    }
    repository = CandidateRepository(db_path=str(tmp_path / "candidates.db"))

    result = ingest_gmail_candidates(
        GmailMailboxClient("token", http_get_fn=lambda path, headers: responses[path]),
        repository,
    )

    assert result == {
        "messages_received": 2,
        "candidates_stored": 1,
        "messages_skipped": 1,
    }
    candidate = repository.list_candidates()[0]
    assert candidate.id == "candidate-gmail-with-resume"
    assert candidate.email == "a@example.com"
    assert candidate.resume_text == "Python FastAPI"
