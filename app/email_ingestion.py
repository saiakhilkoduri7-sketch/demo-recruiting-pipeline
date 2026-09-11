from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.services import CandidateProfile


@dataclass
class EmailAttachment:
    name: str
    content_type: str
    content_bytes: str


def extract_resume_text(attachment: Dict[str, Any]) -> str:
    content_bytes = attachment.get("contentBytes", "")
    content_type = attachment.get("contentType", "")
    name = attachment.get("name", "")

    if not content_bytes:
        return ""

    decoded = base64.b64decode(content_bytes.encode("utf-8")).decode("utf-8", errors="ignore")

    if content_type.lower().startswith("text/") or name.lower().endswith((".txt", ".md", ".csv")):
        return decoded.strip()

    return decoded.strip()


def process_email_message(message: Dict[str, Any]) -> CandidateProfile:
    sender = message.get("from", {}).get("emailAddress", {})
    sender_email = sender.get("address", "")
    sender_name = sender.get("name", "Alice Applicant")

    subject = message.get("subject", "")
    body = message.get("body", {}).get("content", "")

    attachments = message.get("attachments", [])
    resume_text = "\n".join(
        extract_resume_text(item) for item in attachments if extract_resume_text(item)
    )

    if not resume_text:
        resume_text = body.strip()

    candidate = CandidateProfile(
        id=f"candidate-{message.get('id', 'unknown')}",
        name=sender_name,
        email=sender_email,
        phone="",
        resume_text=resume_text,
        skills=[],
    )

    if subject:
        candidate.skills = [subject]

    return candidate
