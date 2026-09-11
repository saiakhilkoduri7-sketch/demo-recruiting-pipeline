from __future__ import annotations

import json
import sqlite3
from typing import List

from app.services import CandidateProfile, JobRequirement, RankedMatch


class CandidateRepository:
    def __init__(self, db_path: str = "candidates.db"):
        self.db_path = db_path
        self._initialize()

    def _initialize(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS candidates (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT,
                    phone TEXT,
                    resume_text TEXT,
                    skills TEXT,
                    experience_years INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rankings (
                    job_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    score REAL NOT NULL,
                    matched_skills TEXT NOT NULL,
                    PRIMARY KEY (job_id, candidate_id)
                )
                """
            )
            conn.commit()

    def _row_to_candidate(self, row: tuple) -> CandidateProfile:
        return CandidateProfile(
            id=row[0],
            name=row[1],
            email=row[2],
            phone=row[3],
            resume_text=row[4],
            skills=json.loads(row[5]) if row[5] else [],
            experience_years=row[6],
        )

    def _row_to_job(self, row: tuple) -> JobRequirement:
        return JobRequirement(
            id=row[0],
            title=row[1],
            description=row[2],
        )

    def _row_to_ranked_match(self, row: tuple) -> RankedMatch:
        return RankedMatch(
            candidate_id=row[1],
            score=row[2],
            matched_skills=json.loads(row[3]) if row[3] else [],
        )

    def save_candidate(self, candidate: CandidateProfile) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO candidates (
                    id, name, email, phone, resume_text, skills, experience_years
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.id,
                    candidate.name,
                    candidate.email,
                    candidate.phone,
                    candidate.resume_text,
                    json.dumps(candidate.skills),
                    candidate.experience_years,
                ),
            )
            conn.commit()

    def save_job(self, job: JobRequirement) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO jobs (id, title, description)
                VALUES (?, ?, ?)
                """,
                (job.id, job.title, job.description),
            )
            conn.commit()

    def save_ranked_matches(self, job_id: str, matches: List[RankedMatch]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            for match in matches:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO rankings (job_id, candidate_id, score, matched_skills)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        match.candidate_id,
                        match.score,
                        json.dumps(match.matched_skills),
                    ),
                )
            conn.commit()

    def list_candidates(self) -> List[CandidateProfile]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, name, email, phone, resume_text, skills, experience_years FROM candidates"
            ).fetchall()
        return [self._row_to_candidate(row) for row in rows]

    def list_jobs(self) -> List[JobRequirement]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, title, description FROM jobs"
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def list_ranked_matches(self, job_id: str) -> List[RankedMatch]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT job_id, candidate_id, score, matched_skills FROM rankings WHERE job_id = ? ORDER BY score DESC",
                (job_id,),
            ).fetchall()
        return [self._row_to_ranked_match(row) for row in rows]
