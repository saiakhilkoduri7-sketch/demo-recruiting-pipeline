from __future__ import annotations

import tempfile
import uuid
from functools import lru_cache
from hmac import compare_digest
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import CandidateRepository
from app.demo_pipeline import _extract_resume_text, load_resume_candidates, run_demo_pipeline
from app.graph_mailbox import GraphMailboxClient, ingest_mailbox_candidates
from app.services import CandidateProfile, JobRequirement, RankedMatch, deduplicate_candidates, rank_candidates


class DemoRequest(BaseModel):
    resume_folder: str = Field(min_length=1, max_length=500)
    job_title: str = Field(min_length=1, max_length=140)
    job_description: str = Field(min_length=1, max_length=10000)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class JobCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    description: str = Field(min_length=1, max_length=10000)


class JobRecord(BaseModel):
    id: str
    title: str
    description: str


class MatchRequest(BaseModel):
    resume_folder: str | None = None


class MailboxIngestRequest(BaseModel):
    mailbox_address: str | None = None
    access_token: str | None = None
    top: int = 10


class RankedMatchResponse(BaseModel):
    candidate_id: str
    candidate_name: str
    score: float
    matched_skills: list[str]


class CandidateDetailResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: str
    resume_text: str
    skills: list[str]
    experience_years: int | None


class CandidateUploadResponse(BaseModel):
    id: str
    name: str
    resume_size: int
    extracted_chars: int


app = FastAPI(
    title="TalentMatch AI",
    description="Demo API for resume ingestion, deduplication, and matching.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.trusted_hosts if settings.is_production else ["*"],
)
@app.middleware("http")
async def enforce_browser_auth(request: Request, call_next):
    public_paths = {"/", "/ui", "/health", "/auth/session", "/auth/login"}
    is_public_static_file = request.url.path.startswith("/static/")
    if settings.is_production and request.method != "OPTIONS":
        if request.method not in {"GET", "HEAD"}:
            origin = request.headers.get("origin")
            if not origin or origin not in settings.allowed_origins:
                return JSONResponse(status_code=403, content={"detail": "Invalid request origin"})

        if (
            request.url.path not in public_paths
            and not is_public_static_file
            and not request.session.get("authenticated")
        ):
            return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path.startswith(("/auth/", "/candidates", "/jobs", "/dashboard")):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="talentmatch_session",
    max_age=8 * 60 * 60,
    same_site="strict",
    https_only=settings.is_production,
)


app.mount("/static", StaticFiles(directory=str(settings.frontend_dir)), name="static")


@lru_cache(maxsize=1)
def get_repository() -> CandidateRepository:
    database_url = settings.database_url
    if database_url:
        return CandidateRepository(db_url=database_url)
    return CandidateRepository(db_path=settings.sqlite_path)


@app.get("/auth/session")
def auth_session(request: Request) -> dict[str, bool]:
    return {
        "authenticated": not settings.is_production or bool(request.session.get("authenticated")),
        "folder_import_enabled": not settings.is_production,
    }


@app.post("/auth/login")
def login(request: Request, credentials: LoginRequest) -> dict[str, bool]:
    if not settings.is_production:
        request.session["authenticated"] = True
        return {"authenticated": True}

    if not (
        compare_digest(credentials.username, settings.admin_username)
        and compare_digest(credentials.password, settings.admin_password)
    ):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    request.session.clear()
    request.session["authenticated"] = True
    return {"authenticated": True}


@app.post("/auth/logout")
def logout(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"authenticated": False}


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "TalentMatch AI API is running",
        "ui": "/ui",
        "health": "/health",
    }


@app.get("/ui")
def ui() -> FileResponse:
    return FileResponse("frontend/index.html")


@app.get("/health")
def health() -> dict[str, str]:
    try:
        get_repository().check_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    return {"status": "ok"}


@app.post("/mailbox/ingest")
def ingest_mailbox(request: MailboxIngestRequest) -> dict[str, int]:
    mailbox_address = request.mailbox_address or settings.outlook_shared_mailbox
    access_token = request.access_token or settings.graph_access_token
    if not mailbox_address.strip() or not access_token.strip():
        raise HTTPException(status_code=400, detail="Mailbox address and Graph access token are required.")
    if request.top < 1 or request.top > 100:
        raise HTTPException(status_code=400, detail="top must be between 1 and 100.")

    repository = get_repository()
    client = GraphMailboxClient(access_token=access_token)
    return ingest_mailbox_candidates(
        client=client,
        repository=repository,
        mailbox_address=mailbox_address.strip(),
        top=request.top,
    )


@app.get("/dashboard/stats")
def dashboard_stats() -> dict:
    repository = get_repository()
    jobs = repository.list_jobs()
    candidates = repository.list_candidates()

    total_matches = 0
    total_score = 0.0
    qualified = 0
    jobs_summary: list[dict] = []

    for job in jobs:
        matches = repository.list_ranked_matches(job.id)
        total_matches += len(matches)
        total_score += sum(match.score for match in matches)
        qualified += sum(1 for match in matches if match.score >= 80)
        jobs_summary.append(
            {
                "job_id": job.id,
                "title": job.title,
                "match_count": len(matches),
                "top_score": max((match.score for match in matches), default=0.0),
            }
        )

    avg_score = round((total_score / total_matches), 2) if total_matches else 0.0

    return {
        "active_jobs": len(jobs),
        "total_candidates": len(candidates),
        "average_score": avg_score,
        "qualified_candidates": qualified,
        "job_summary": jobs_summary,
    }


@app.get("/candidates")
def list_candidates() -> list[dict]:
    repository = get_repository()
    return [
        {
            "id": candidate.id,
            "name": candidate.name,
            "email": candidate.email or "N/A",
            "skills": candidate.skills,
        }
        for candidate in repository.list_candidates()
    ]


@app.get("/candidates/search")
def search_candidates(name: str = "") -> list[dict]:
    repository = get_repository()
    query = name.strip().lower()
    candidates = repository.list_candidates()
    if not query:
        return [
            {
                "id": candidate.id,
                "name": candidate.name,
                "email": candidate.email or "N/A",
                "skills": candidate.skills,
            }
            for candidate in candidates
        ]

    filtered = [
        candidate for candidate in candidates
        if query in candidate.name.lower() or query in (candidate.email or "").lower()
    ]
    return [
        {
            "id": candidate.id,
            "name": candidate.name,
            "email": candidate.email or "N/A",
            "skills": candidate.skills,
        }
        for candidate in filtered
    ]


@app.get("/candidates/{candidate_id}")
def get_candidate_detail(candidate_id: str) -> CandidateDetailResponse:
    repository = get_repository()
    for candidate in repository.list_candidates():
        if candidate.id == candidate_id:
            return CandidateDetailResponse(
                id=candidate.id,
                name=candidate.name,
                email=candidate.email,
                phone=candidate.phone,
                resume_text=candidate.resume_text,
                skills=candidate.skills,
                experience_years=candidate.experience_years,
            )
    raise HTTPException(status_code=404, detail="Candidate not found")


@app.delete("/candidates/{candidate_id}")
def delete_candidate(candidate_id: str) -> dict:
    repository = get_repository()
    repository.delete_candidate(candidate_id)
    return {"status": "deleted", "candidate_id": candidate_id}


@app.post("/candidates/upload")
def upload_candidate(
    file: UploadFile = File(...),
    candidate_name: str | None = Query(default=None, max_length=140),
) -> CandidateUploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A resume file is required.")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".txt", ".md", ".csv", ".pdf", ".docx"}:
        raise HTTPException(status_code=415, detail="Upload a TXT, MD, CSV, PDF, or DOCX resume.")

    contents = file.file.read(settings.max_resume_size_bytes + 1)
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(contents) > settings.max_resume_size_bytes:
        raise HTTPException(status_code=413, detail="Resume files must be 10 MB or smaller.")

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(contents)
            temp_path = Path(temp_file.name)

        resume_text = _extract_resume_text(temp_path)
        if not resume_text.strip():
            raise HTTPException(status_code=400, detail="Unable to extract text from the uploaded file.")

        candidate_id = f"{Path(file.filename).stem}-{uuid.uuid4().hex[:8]}"
        name = (candidate_name or Path(file.filename).stem).strip() or "Candidate"

        candidate = CandidateProfile(
            id=candidate_id,
            name=name,
            email="",
            phone="",
            resume_text=resume_text,
            skills=[],
            experience_years=None,
        )

        repository = get_repository()
        repository.save_candidate(candidate)

        return CandidateUploadResponse(
            id=candidate.id,
            name=candidate.name,
            resume_size=len(contents),
            extracted_chars=len(resume_text),
        )
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


@app.get("/jobs")
def list_jobs() -> list[JobRecord]:
    repository = get_repository()
    jobs = repository.list_jobs()
    return [JobRecord(id=job.id, title=job.title, description=job.description) for job in jobs]


@app.post("/jobs")
def create_job(request: JobCreateRequest) -> JobRecord:
    if not request.title.strip() or not request.description.strip():
        raise HTTPException(status_code=400, detail="Job title and description are required.")

    repository = get_repository()
    job = JobRequirement(
        id=str(uuid.uuid4()),
        title=request.title.strip(),
        description=request.description.strip(),
    )
    repository.save_job(job)
    return JobRecord(id=job.id, title=job.title, description=job.description)


@app.delete("/jobs/{job_id}")
def delete_job(job_id: str) -> dict:
    repository = get_repository()
    repository.delete_job(job_id)
    return {"status": "deleted", "job_id": job_id}


@app.get("/jobs/{job_id}/results")
def get_job_results(job_id: str) -> list[RankedMatchResponse]:
    repository = get_repository()
    stored = repository.list_ranked_matches(job_id)
    if not stored:
        return []

    candidates = {candidate.id: candidate for candidate in repository.list_candidates()}
    response: list[RankedMatchResponse] = []
    for match in stored:
        candidate_record = candidates.get(match.candidate_id)
        response.append(
            RankedMatchResponse(
                candidate_id=match.candidate_id,
                candidate_name=candidate_record.name if candidate_record else match.candidate_id,
                score=match.score,
                matched_skills=match.matched_skills,
            )
        )
    return response


@app.post("/jobs/{job_id}/match")
def run_match_for_job(job_id: str, request: MatchRequest) -> dict:
    repository = get_repository()
    job = next((job for job in repository.list_jobs() if job.id == job_id), None)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if not request.resume_folder:
        return run_database_match_for_job(job_id)
    if settings.is_production:
        raise HTTPException(
            status_code=400,
            detail="Server-folder imports are disabled in production. Upload resumes instead.",
        )

    resume_folder = Path(request.resume_folder)
    if not resume_folder.exists() or not resume_folder.is_dir():
        raise HTTPException(status_code=400, detail=f"Resume folder not found: {resume_folder}")

    candidate_records = load_resume_candidates(str(resume_folder))
    for candidate in candidate_records:
        repository.save_candidate(candidate)

    results = run_demo_pipeline(
        resume_folder=str(resume_folder),
        job_title=job.title,
        job_description=job.description,
    )

    ranked_matches = [
        RankedMatch(
            candidate_id=item["candidate_id"],
            score=float(item["score"]),
            matched_skills=list(item["matched_skills"]),
        )
        for item in results["agent2"]
    ]
    repository.save_ranked_matches(job_id, ranked_matches)

    return {
        "job_id": job_id,
        "summary": results["agent1"],
        "matches": results["agent2"],
    }


@app.post("/jobs/{job_id}/match-database")
def run_database_match_for_job(job_id: str) -> dict:
    repository = get_repository()
    job = next((job for job in repository.list_jobs() if job.id == job_id), None)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    candidates = repository.list_candidates()
    unique_candidates, duplicates = deduplicate_candidates(candidates)
    ranked = rank_candidates(job, unique_candidates)
    repository.save_ranked_matches(job_id, ranked)

    candidates_by_id = {candidate.id: candidate for candidate in unique_candidates}
    matches = [
        {
            "candidate_id": match.candidate_id,
            "candidate_name": candidates_by_id[match.candidate_id].name,
            "score": match.score,
            "matched_skills": match.matched_skills,
        }
        for match in ranked
    ]
    return {
        "job_id": job_id,
        "source": "database",
        "summary": {
            "total_candidates": len(candidates),
            "unique_candidates": len(unique_candidates),
            "duplicates": len(duplicates),
        },
        "matches": matches,
    }


@app.post("/run-demo")
def run_demo(request: DemoRequest) -> dict:
    if settings.is_production:
        raise HTTPException(status_code=404, detail="Demo endpoint is unavailable in production.")

    resume_folder = Path(request.resume_folder)

    if not resume_folder.exists() or not resume_folder.is_dir():
        raise HTTPException(status_code=400, detail=f"Resume folder not found: {resume_folder}")

    return run_demo_pipeline(
        resume_folder=str(resume_folder),
        job_title=request.job_title,
        job_description=request.job_description,
    )
