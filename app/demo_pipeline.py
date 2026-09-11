from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.services import CandidateProfile, JobRequirement, deduplicate_candidates, rank_candidates


def _extract_text_from_pdf(file_path: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""

    reader = PdfReader(str(file_path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def _extract_text_from_docx(file_path: Path) -> str:
    try:
        from docx import Document
    except Exception:
        return ""

    document = Document(str(file_path))
    paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    return "\n".join(paragraphs).strip()


def _extract_resume_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()

    if suffix in {".txt", ".md", ".csv"}:
        return file_path.read_text(encoding="utf-8", errors="ignore").strip()

    if suffix == ".pdf":
        return _extract_text_from_pdf(file_path)

    if suffix == ".docx":
        return _extract_text_from_docx(file_path)

    return ""


def load_resume_candidates(resume_folder: str) -> List[CandidateProfile]:
    folder = Path(resume_folder)
    candidates: List[CandidateProfile] = []

    for file_path in sorted(folder.iterdir()):
        if not file_path.is_file():
            continue

        text = _extract_resume_text(file_path)
        if not text:
            continue

        candidate_name = file_path.stem.lower()
        candidates.append(
            CandidateProfile(
                id=file_path.stem,
                name=candidate_name,
                email="",
                phone="",
                resume_text=text,
                skills=[],
            )
        )

    return candidates


def run_demo_pipeline(resume_folder: str, job_title: str, job_description: str) -> Dict[str, Any]:
    candidates = load_resume_candidates(resume_folder)
    unique_candidates, duplicates = deduplicate_candidates(candidates)

    job = JobRequirement(
        id="demo-job",
        title=job_title,
        description=job_description,
    )

    ranked = rank_candidates(job, unique_candidates)

    agent2_output = []
    for item in ranked:
        candidate = next(candidate for candidate in unique_candidates if candidate.id == item.candidate_id)
        agent2_output.append(
            {
                "candidate_id": item.candidate_id,
                "candidate_name": candidate.name,
                "score": item.score,
                "matched_skills": item.matched_skills,
            }
        )

    return {
        "agent1": {
            "total_candidates": len(candidates),
            "unique_candidates": len(unique_candidates),
            "duplicates": len(duplicates),
        },
        "agent2": agent2_output,
    }
