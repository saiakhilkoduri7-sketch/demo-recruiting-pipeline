from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import md5
from typing import List, Tuple


@dataclass
class CandidateProfile:
    id: str
    name: str
    email: str = ""
    phone: str = ""
    resume_text: str = ""
    skills: List[str] = field(default_factory=list)
    experience_years: int | None = None


@dataclass
class JobRequirement:
    id: str
    title: str
    description: str


@dataclass
class RankedMatch:
    candidate_id: str
    score: float
    matched_skills: List[str]


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _normalize_phone(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def _extract_keywords(text: str) -> set[str]:
    stop_words = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "for",
        "to",
        "of",
        "in",
        "on",
        "with",
        "at",
        "by",
        "from",
        "is",
        "are",
        "be",
        "as",
        "that",
        "this",
        "into",
        "over",
        "under",
        "our",
        "we",
        "you",
        "your",
    }

    collection: set[str] = set()
    for token in text.replace("/", " ").replace("-", " ").split():
        cleaned = token.strip(".,:;()[]{}!?").lower()
        if len(cleaned) > 2 and cleaned not in stop_words:
            collection.add(cleaned)
    return collection


def compute_resume_fingerprint(resume_text: str) -> str:
    normalized = _normalize_text(resume_text)
    return md5(normalized.encode("utf-8"), usedforsecurity=False).hexdigest()


def deduplicate_candidates(candidates: List[CandidateProfile]) -> Tuple[List[CandidateProfile], List[CandidateProfile]]:
    unique_candidates: List[CandidateProfile] = []
    duplicates: List[CandidateProfile] = []

    seen_emails: set[str] = set()
    seen_phones: set[str] = set()
    seen_fingerprints: set[str] = set()

    for candidate in candidates:
        email_key = _normalize_text(candidate.email)
        phone_key = _normalize_phone(candidate.phone)
        normalized_resume = _normalize_text(candidate.resume_text)
        fingerprint = compute_resume_fingerprint(normalized_resume) if normalized_resume else ""

        duplicate_match = (
            email_key and email_key in seen_emails
        ) or (
            phone_key and phone_key in seen_phones
        ) or fingerprint in seen_fingerprints

        if duplicate_match:
            duplicates.append(candidate)
            continue

        if email_key:
            seen_emails.add(email_key)
        if phone_key:
            seen_phones.add(phone_key)
        if fingerprint:
            seen_fingerprints.add(fingerprint)

        unique_candidates.append(candidate)

    return unique_candidates, duplicates


def rank_candidates(job: JobRequirement, candidates: List[CandidateProfile]) -> List[RankedMatch]:
    job_keywords = _extract_keywords(f"{job.title} {job.description}")

    ranked: List[RankedMatch] = []

    for candidate in candidates:
        candidate_keywords = _extract_keywords(
            f"{candidate.name} {' '.join(candidate.skills)} {candidate.resume_text}"
        )

        matched_skills = sorted(job_keywords.intersection(candidate_keywords))

        if not matched_skills or not job_keywords:
            score = 0.0
        else:
            score = round((len(matched_skills) / len(job_keywords)) * 100, 2)

        ranked.append(
            RankedMatch(
                candidate_id=candidate.id,
                score=score,
                matched_skills=matched_skills,
            )
        )

    ranked.sort(key=lambda item: (item.score, item.candidate_id), reverse=True)
    return ranked
