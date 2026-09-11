from app.graph_mailbox import GraphMailboxClient, extract_candidates_from_messages


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
