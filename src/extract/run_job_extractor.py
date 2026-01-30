#!/usr/bin/env python3
"""
Run the job extractor: read career links file, extract jobs, write data/jobs.json.
Usage: python run_job_extractor.py [--links data/all_links.txt]
"""

import sys
from pathlib import Path

# Project root (avature-scraper/) for data paths and imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.extract.job_extractor import run_extraction


def main():
    # Prefer all_links.txt (includes job URLs) if present; else avature_career_links.txt
    links_candidates = [
        PROJECT_ROOT / "data" / "all_links.txt",
        PROJECT_ROOT / "src" / "data" / "all_links.txt",
        PROJECT_ROOT / "src" / "crawler" / "data" / "all_links.txt",
        PROJECT_ROOT / "data" / "avature_career_links.txt",
        PROJECT_ROOT / "src" / "data" / "avature_career_links.txt",
        PROJECT_ROOT / "src" / "crawler" / "data" / "avature_career_links.txt",
    ]
    links_file = None
    for p in links_candidates:
        if p.exists():
            links_file = p
            break
    if not links_file:
        links_file = PROJECT_ROOT / "data" / "avature_career_links.txt"
        links_file.parent.mkdir(parents=True, exist_ok=True)
        print(f"No links file found. Create {links_file} with one URL per line, or run the career crawler first.")

    output_file = PROJECT_ROOT / "data" / "jobs.json"
    run_extraction(
        links_file=str(links_file),
        output_file=str(output_file),
        fetch_rss=True,
        fetch_job_pages=True,
        max_job_pages=500,
    )

if __name__ == "__main__":
    main()
