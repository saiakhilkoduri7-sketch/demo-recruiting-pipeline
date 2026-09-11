from app.email_ingestion import extract_resume_text, process_email_message


def test_extract_resume_text_from_plaintext_attachment():
    attachment = {
        "name": "resume.txt",
        "contentType": "text/plain",
        "contentBytes": "U29tZSBSZXN1bWUgdGV4dA==",
    }

    text = extract_resume_text(attachment)

    assert text == "Some Resume text"


def test_process_email_message_builds_candidate_profile():
    message = {
        "id": "msg-1",
        "subject": "Application for Senior Python Engineer",
        "body": {"content": "Please consider me for this role."},
        "from": {"emailAddress": {"address": "applicant@example.com", "name": "Alice Applicant"}},
        "attachments": [
            {
                "name": "resume.txt",
                "contentType": "text/plain",
                "contentBytes": "U2tpbGxzOiBQeXRob24sIEZhc3RBUEksIFBvc3RncmVTUUw=",
            }
        ],
    }

    candidate = process_email_message(message)

    assert candidate.email == "applicant@example.com"
    assert candidate.name == "Alice Applicant"
    assert candidate.resume_text == "Skills: Python, FastAPI, PostgreSQL"
