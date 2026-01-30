#!/usr/bin/env python3
"""Run the Avature career crawler. Output: project data/avature_career_links.txt, data/all_links.txt."""

import sys
from pathlib import Path

# Project root (avature-scraper/) for data paths and imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.crawler.career_crawler import crawl

if __name__ == "__main__":
    crawl(output_dir=str(PROJECT_ROOT / "data"), validate=True, include_job_links=True)
