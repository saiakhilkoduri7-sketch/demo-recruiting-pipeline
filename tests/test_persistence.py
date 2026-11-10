from app.database import CandidateRepository
from app.services import CandidateProfile, JobRequirement, RankedMatch


def test_repository_persists_candidates(tmp_path):
    db_path = tmp_path / "candidates.db"
    repository = CandidateRepository(db_path=str(db_path))

    candidate = CandidateProfile(
        id="c1",
        name="Alice",
        email="alice@example.com",
        phone="555-1234",
        resume_text="Python FastAPI PostgreSQL",
        skills=["Python", "FastAPI", "PostgreSQL"],
    )

    repository.save_candidate(candidate)
    loaded = repository.list_candidates()

    assert len(loaded) == 1
    assert loaded[0].email == "alice@example.com"
    assert loaded[0].skills == ["Python", "FastAPI", "PostgreSQL"]


def test_repository_persists_and_deletes_original_candidate_resumes(tmp_path):
    repository = CandidateRepository(db_path=str(tmp_path / "candidate-files.db"))
    candidate = CandidateProfile(id="candidate-1", name="Alice", resume_text="Python")
    file_contents = b"original resume bytes"

    repository.save_candidate(
        candidate,
        resumes=[("resume-1.pdf", "application/pdf", file_contents)],
    )

    assert repository.list_candidate_resumes("candidate-1") == [
        {
            "id": "candidate-1-0",
            "filename": "resume-1.pdf",
            "content_type": "application/pdf",
        }
    ]
    assert repository.get_candidate_resume("candidate-1", "candidate-1-0") == (
        "resume-1.pdf",
        "application/pdf",
        file_contents,
    )
    assert repository.get_candidate_resume("different-candidate", "candidate-1-0") is None

    repository.delete_candidate("candidate-1")

    assert repository.list_candidate_resumes("candidate-1") == []


def test_repository_persists_job_matches(tmp_path):
    db_path = tmp_path / "matches.db"
    repository = CandidateRepository(db_path=str(db_path))

    job = JobRequirement(
        id="job-1",
        title="Senior Python Engineer",
        description="Python, FastAPI, PostgreSQL, cloud deployment",
    )

    repository.save_job(job)

    ranked = [
        RankedMatch(candidate_id="c1", score=95.0, matched_skills=["python", "fastapi"]),
        RankedMatch(candidate_id="c2", score=60.0, matched_skills=["python"]),
    ]

    repository.save_ranked_matches(job.id, ranked)

    stored = repository.list_ranked_matches(job.id)

    assert len(stored) == 2
    assert stored[0].score == 95.0
    assert stored[0].matched_skills == ["python", "fastapi"]
