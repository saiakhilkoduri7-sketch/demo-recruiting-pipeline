import importlib

from fastapi.testclient import TestClient

from app.database import CandidateRepository
from app.services import CandidateProfile


def test_candidate_detail_includes_downloadable_original_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    import app.config as config_module

    importlib.reload(config_module)
    import app.api as api_module

    api_module = importlib.reload(api_module)
    repository = CandidateRepository(db_path=str(tmp_path / "resume-download.db"))
    candidate = CandidateProfile(
        id="candidate-one",
        name="Demo Candidate",
        email="demo@example.com",
        resume_text="Python experience",
    )
    repository.save_candidate(
        candidate,
        resumes=[
            ("résumé demo.pdf", "application/pdf", b"%PDF-demo-resume"),
            ("details.txt", "text/plain", b"additional details"),
        ],
    )
    monkeypatch.setattr(api_module, "get_repository", lambda: repository)
    client = TestClient(api_module.app)

    detail = client.get("/candidates/candidate-one")

    assert detail.status_code == 200
    resumes = detail.json()["resumes"]
    assert [resume["filename"] for resume in resumes] == [
        "résumé demo.pdf",
        "details.txt",
    ]
    assert "content" not in resumes[0]

    download = client.get(
        f"/candidates/candidate-one/resumes/{resumes[0]['id']}/download"
    )

    assert download.status_code == 200
    assert download.content == b"%PDF-demo-resume"
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"] == (
        "attachment; filename*=UTF-8''r%C3%A9sum%C3%A9%20demo.pdf"
    )
    assert download.headers["cache-control"] == "no-store"
    assert client.get(
        "/candidates/not-the-owner/resumes/candidate%2Fone-0/download"
    ).status_code == 404
