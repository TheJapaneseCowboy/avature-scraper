#!/usr/bin/env python3
"""
Run the full Avature scraper pipeline:
  1. Crawler  – discover career sites, write data/avature_career_links.txt and data/all_links.txt
  2. Extractor – read links from data/ (initial_links.txt, all_links.txt, avature_career_links.txt),
                 extract jobs, write data/jobs.json

Run from project root:  python run_all.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    print("=== Step 1: Crawler (discover career links) ===")
    from src.crawler.career_crawler import crawl
    crawl(output_dir=str(PROJECT_ROOT / "data"), validate=True, include_job_links=True)

    print("\n=== Step 2: Job extractor (extract jobs into data/jobs.json) ===")
    from src.extract.job_extractor import run_extraction
    data_dir = PROJECT_ROOT / "data"
    links_files = [
        data_dir / "initial_links.txt",
        data_dir / "all_links.txt",
        data_dir / "avature_career_links.txt",
    ]
    existing = [str(p) for p in links_files if p.exists()]
    if not existing:
        existing = [str(data_dir / "avature_career_links.txt")]
    run_extraction(
        links_files=existing,
        output_file=str(data_dir / "jobs.json"),
        fetch_rss=True,
        fetch_job_pages=True,
        max_job_pages=500,
    )
    print("\nDone. Output: data/jobs.json")


if __name__ == "__main__":
    main()
