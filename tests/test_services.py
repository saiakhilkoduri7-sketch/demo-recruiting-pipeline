from hashlib import md5

from app.services import (
    CandidateProfile,
    JobRequirement,
    RankedMatch,
    compute_resume_fingerprint,
    deduplicate_candidates,
    rank_candidates,
)


def test_compute_resume_fingerprint_is_stable():
    text = "John Doe\nPython, FastAPI, PostgreSQL"

    fingerprint = compute_resume_fingerprint(text)

    expected = md5("john doe python, fastapi, postgresql".encode("utf-8")).hexdigest()
    assert fingerprint == expected


def test_deduplicate_candidates_uses_contact_and_resume_fingerprint():
    candidates = [
        CandidateProfile(
            id="c1",
            name="Alice",
            email="alice@example.com",
            phone="555-1234",
            resume_text="Python FastAPI PostgreSQL",
        ),
        CandidateProfile(
            id="c2",
            name="Alice Duplicate",
            email="alice@example.com",
            phone="555-1234",
            resume_text="Python FastAPI PostgreSQL",
        ),
    ]

    unique_candidates, duplicates = deduplicate_candidates(candidates)

    assert len(unique_candidates) == 1
    assert len(duplicates) == 1
    assert duplicates[0].id == "c2"


def test_deduplicate_candidates_normalizes_phone_formatting():
    candidates = [
        CandidateProfile(id="c1", name="Alice", phone="(555) 123-4567"),
        CandidateProfile(id="c2", name="Alice Duplicate", phone="5551234567"),
    ]

    unique_candidates, duplicates = deduplicate_candidates(candidates)

    assert [candidate.id for candidate in unique_candidates] == ["c1"]
    assert [candidate.id for candidate in duplicates] == ["c2"]


def test_deduplicate_candidates_does_not_match_empty_resumes():
    candidates = [
        CandidateProfile(id="c1", name="Alice", resume_text=""),
        CandidateProfile(id="c2", name="Bob", resume_text="  \n "),
    ]

    unique_candidates, duplicates = deduplicate_candidates(candidates)

    assert [candidate.id for candidate in unique_candidates] == ["c1", "c2"]
    assert duplicates == []


def test_rank_candidates_returns_ordered_matches():
    job = JobRequirement(
        id="job-1",
        title="Senior Python Engineer",
        description="Need Python, FastAPI, PostgreSQL, and cloud deployment experience.",
    )

    candidates = [
        CandidateProfile(
            id="c1",
            name="Candidate One",
            email="one@example.com",
            phone="111",
            resume_text="Python FastAPI PostgreSQL Docker Kubernetes",
        ),
        CandidateProfile(
            id="c2",
            name="Candidate Two",
            email="two@example.com",
            phone="222",
            resume_text="Java Spring Boot AWS",
        ),
    ]

    ranked = rank_candidates(job, candidates)

    assert ranked[0].candidate_id == "c1"
    assert ranked[0].score > ranked[1].score
    assert isinstance(ranked[0], RankedMatch)
