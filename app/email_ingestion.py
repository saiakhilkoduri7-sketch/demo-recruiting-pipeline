from __future__ import annotations

import base64
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from app.demo_pipeline import _extract_resume_text
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

    decoded_bytes = base64.b64decode(content_bytes.encode("utf-8"))

    if content_type.lower().startswith("text/") or name.lower().endswith((".txt", ".md", ".csv")):
        return decoded_bytes.decode("utf-8", errors="ignore").strip()

    suffix = Path(name).suffix.lower()
    if suffix in {".pdf", ".docx"}:
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(decoded_bytes)
                temp_path = Path(temp_file.name)
            return _extract_resume_text(temp_path)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    return decoded_bytes.decode("utf-8", errors="ignore").strip()


def process_email_message(message: Dict[str, Any]) -> CandidateProfile:
    sender = message.get("from", {}).get("emailAddress", {})
    sender_email = sender.get("address", "")
    sender_name = sender.get("name", "Alice Applicant")

    subject = message.get("subject", "")
    body = message.get("body", {}).get("content", "")

    attachments = message.get("attachments", [])
    extracted_resumes = [extract_resume_text(item) for item in attachments]
    resume_text = "\n".join(text for text in extracted_resumes if text)

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
