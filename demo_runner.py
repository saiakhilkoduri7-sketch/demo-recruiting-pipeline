from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.demo_pipeline import run_demo_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run TalentMatch AI against a folder of resume files.")
    parser.add_argument("--resume-folder", required=True, help="Folder containing resume text files (.txt, .md, .csv).")
    parser.add_argument("--job-title", required=True, help="Job title used for matching.")
    parser.add_argument("--job-description", required=True, help="Job description used for matching.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    resume_folder = Path(args.resume_folder)

    if not resume_folder.exists() or not resume_folder.is_dir():
        raise SystemExit(f"Resume folder not found: {resume_folder}")

    results = run_demo_pipeline(
        resume_folder=str(resume_folder),
        job_title=args.job_title,
        job_description=args.job_description,
    )

    print("Agent 1 summary:")
    print(json.dumps(results["agent1"], indent=2))
    print("\nAgent 2 ranked shortlist:")
    print(json.dumps(results["agent2"], indent=2))


if __name__ == "__main__":
    main()
