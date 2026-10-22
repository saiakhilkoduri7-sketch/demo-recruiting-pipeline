from app.database import CandidateRepository
from app.graph_mailbox import GraphMailboxClient, extract_candidates_from_messages, ingest_mailbox_candidates


def test_graph_mailbox_client_fetches_enriched_messages():
    responses = {
        "/users/jobs@intensify.com/messages?$top=10&$filter=isRead eq false": {
            "value": [
                {
                    "id": "msg-1",
                }
            ]
        },
        "/users/jobs@intensify.com/messages/msg-1": {
            "id": "msg-1",
            "subject": "Application for Senior Python Engineer",
            "body": {"content": "Please consider me for this role."},
            "from": {
                "emailAddress": {
                    "address": "applicant@example.com",
                    "name": "Alice Applicant",
                }
            },
        },
        "/users/jobs@intensify.com/messages/msg-1/attachments": {
            "value": [
                {
                    "name": "resume.txt",
                    "contentType": "text/plain",
                    "contentBytes": "U29tZSBSdW1lIHRleHQ=",
                }
            ]
        },
    }

    client = GraphMailboxClient(
        access_token="test-token",
        http_get_fn=lambda path, headers: responses[path],
    )

    messages = client.fetch_enriched_messages("jobs@intensify.com", top=10)

    assert len(messages) == 1
    assert messages[0]["attachments"][0]["name"] == "resume.txt"


def test_extract_candidates_from_messages_builds_profiles():
    messages = [
        {
            "id": "msg-1",
            "subject": "Application for Senior Python Engineer",
            "body": {"content": "Please consider me for this role."},
            "from": {
                "emailAddress": {
                    "address": "applicant@example.com",
                    "name": "Alice Applicant",
                }
            },
            "attachments": [
                {
                    "name": "resume.txt",
                    "contentType": "text/plain",
                    "contentBytes": "U29tZSBSZXN1bWUgdGV4dA==",
                }
            ],
        }
    ]

    candidates = extract_candidates_from_messages(messages)

    assert len(candidates) == 1
    assert candidates[0].email == "applicant@example.com"
    assert candidates[0].resume_text == "Some Resume text"


def test_ingest_mailbox_candidates_persists_resumes(tmp_path):
    message = {
        "id": "msg-1",
        "from": {"emailAddress": {"address": "applicant@example.com", "name": "Alice Applicant"}},
        "attachments": [
            {
                "name": "resume.txt",
                "contentType": "text/plain",
                "contentBytes": "UHl0aG9uIEZhc3RBUEk=",
            }
        ],
    }
    client = GraphMailboxClient(
        access_token="test-token",
        http_get_fn=lambda path, headers: (
            {"value": [message]}
            if "?$top=" in path
            else {"value": [{"name": "resume.txt", "contentType": "text/plain", "contentBytes": "UHl0aG9uIEZhc3RBUEk="}]}
            if path.endswith("/attachments")
            else message
        ),
    )
    repository = CandidateRepository(db_path=str(tmp_path / "candidates.db"))

    result = ingest_mailbox_candidates(client, repository, "jobs@example.com")

    assert result == {"messages_received": 1, "candidates_stored": 1, "messages_skipped": 0}
    assert repository.list_candidates()[0].id == "candidate-msg-1"
