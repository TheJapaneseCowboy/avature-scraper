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
    # Use initial_links.txt first, then merge with other link files that exist
    data_dir = PROJECT_ROOT / "data"
    links_files = [
        data_dir / "initial_links.txt",
        data_dir / "all_links.txt",
        data_dir / "avature_career_links.txt",
    ]
    # Use all link files that exist (initial_links.txt first when present)
    existing = [str(p) for p in links_files if p.exists()]
    if not existing:
        data_dir.mkdir(parents=True, exist_ok=True)
        default = data_dir / "avature_career_links.txt"
        print(f"No link files found. Create {data_dir / 'initial_links.txt'} or run the career crawler first.")
        existing = [str(default)]

    output_file = PROJECT_ROOT / "data" / "jobs.json"
    run_extraction(
        links_files=existing,
        output_file=str(output_file),
        fetch_rss=True,
        fetch_job_pages=True,
        max_job_pages=500,
    )

if __name__ == "__main__":
    main()
