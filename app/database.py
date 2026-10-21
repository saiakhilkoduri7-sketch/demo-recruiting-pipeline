from __future__ import annotations

import json
import os
import sqlite3
from typing import List

try:
    import psycopg2
except Exception:  # pragma: no cover - optional dependency
    psycopg2 = None

from app.services import CandidateProfile, JobRequirement, RankedMatch


class CandidateRepository:
    def __init__(self, db_path: str = "candidates.db", db_url: str | None = None):
        self.db_path = db_path
        self.db_url = db_url or os.getenv("DATABASE_URL")
        self._initialize()

    def _uses_postgres(self) -> bool:
        return bool(self.db_url)

    def _connect_sqlite(self):
        return sqlite3.connect(self.db_path)

    def _connect_postgres(self):
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is required when DATABASE_URL is configured.")
        return psycopg2.connect(self.db_url, connect_timeout=10)

    def check_connection(self) -> None:
        if self._uses_postgres():
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            return

        with self._connect_sqlite() as conn:
            conn.execute("SELECT 1")

    def _initialize(self) -> None:
        if self._uses_postgres():
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute(
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
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS jobs (
                            id TEXT PRIMARY KEY,
                            title TEXT NOT NULL,
                            description TEXT NOT NULL
                        )
                        """
                    )
                    cur.execute(
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
            return

        with self._connect_sqlite() as conn:
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
        if self._uses_postgres():
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO candidates (id, name, email, phone, resume_text, skills, experience_years)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id)
                        DO UPDATE SET
                            name = EXCLUDED.name,
                            email = EXCLUDED.email,
                            phone = EXCLUDED.phone,
                            resume_text = EXCLUDED.resume_text,
                            skills = EXCLUDED.skills,
                            experience_years = EXCLUDED.experience_years
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
            return

        with self._connect_sqlite() as conn:
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
        if self._uses_postgres():
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO jobs (id, title, description)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (id)
                        DO UPDATE SET
                            title = EXCLUDED.title,
                            description = EXCLUDED.description
                        """,
                        (job.id, job.title, job.description),
                    )
                conn.commit()
            return

        with self._connect_sqlite() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO jobs (id, title, description)
                VALUES (?, ?, ?)
                """,
                (job.id, job.title, job.description),
            )
            conn.commit()

    def save_ranked_matches(self, job_id: str, matches: List[RankedMatch]) -> None:
        if self._uses_postgres():
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    for match in matches:
                        cur.execute(
                            """
                            INSERT INTO rankings (job_id, candidate_id, score, matched_skills)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (job_id, candidate_id)
                            DO UPDATE SET
                                score = EXCLUDED.score,
                                matched_skills = EXCLUDED.matched_skills
                            """,
                            (
                                job_id,
                                match.candidate_id,
                                match.score,
                                json.dumps(match.matched_skills),
                            ),
                        )
                conn.commit()
            return

        with self._connect_sqlite() as conn:
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

    def delete_candidate(self, candidate_id: str) -> None:
        if self._uses_postgres():
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM rankings WHERE candidate_id = %s", (candidate_id,))
                    cur.execute("DELETE FROM candidates WHERE id = %s", (candidate_id,))
                conn.commit()
            return

        with self._connect_sqlite() as conn:
            conn.execute("DELETE FROM rankings WHERE candidate_id = ?", (candidate_id,))
            conn.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))
            conn.commit()

    def delete_job(self, job_id: str) -> None:
        if self._uses_postgres():
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM rankings WHERE job_id = %s", (job_id,))
                    cur.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
                conn.commit()
            return

        with self._connect_sqlite() as conn:
            conn.execute("DELETE FROM rankings WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            conn.commit()

    def list_candidates(self) -> List[CandidateProfile]:
        if self._uses_postgres():
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, name, email, phone, resume_text, skills, experience_years FROM candidates"
                    )
                    rows = cur.fetchall()
            return [self._row_to_candidate(row) for row in rows]

        with self._connect_sqlite() as conn:
            rows = conn.execute(
                "SELECT id, name, email, phone, resume_text, skills, experience_years FROM candidates"
            ).fetchall()
        return [self._row_to_candidate(row) for row in rows]

    def list_jobs(self) -> List[JobRequirement]:
        if self._uses_postgres():
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id, title, description FROM jobs")
                    rows = cur.fetchall()
            return [self._row_to_job(row) for row in rows]

        with self._connect_sqlite() as conn:
            rows = conn.execute(
                "SELECT id, title, description FROM jobs"
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def list_ranked_matches(self, job_id: str) -> List[RankedMatch]:
        if self._uses_postgres():
            with self._connect_postgres() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT job_id, candidate_id, score, matched_skills FROM rankings WHERE job_id = %s ORDER BY score DESC",
                        (job_id,),
                    )
                    rows = cur.fetchall()
            return [self._row_to_ranked_match(row) for row in rows]

        with self._connect_sqlite() as conn:
            rows = conn.execute(
                "SELECT job_id, candidate_id, score, matched_skills FROM rankings WHERE job_id = ? ORDER BY score DESC",
                (job_id,),
            ).fetchall()
        return [self._row_to_ranked_match(row) for row in rows]
