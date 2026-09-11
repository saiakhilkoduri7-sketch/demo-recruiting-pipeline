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
