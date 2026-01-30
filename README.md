# Avature Scraper

A Python tool that discovers career sites powered by the [Avature](https://www.avature.net/) ATS and extracts job listings into a single JSON file.

## Features

- **Crawler** – Finds Avature career sites via Certificate Transparency (crt.sh) and DuckDuckGo search, validates them, and collects links (including RSS).
- **Job extractor** – Reads career links from `data/initial_links.txt` (and other link files), fetches RSS and HTML, parses listing pages for individual job links, and extracts job title, description, application URL, and metadata into `data/jobs.json`.
- **RSS filtering** – Only real job postings are kept; blog and marketing content from the vendor site are excluded.
- **Listing-page support** – For SearchJobs-style URLs, the extractor discovers all job detail links on the page and fetches each one so you get multiple jobs per site.

All output files (`.txt`, `.json`) are written under the `data/` folder.

## Requirements

- Python 3.10+
- Dependencies in `requirements.txt`

## Installation

```bash
git clone https://github.com/your-username/avature-scraper.git
cd avature-scraper
pip install -r requirements.txt
```

## Usage

Run from the **project root**. The full pipeline may take **2–3 minutes** (or more with many links) due to HTTP requests and rate limiting.

### Full pipeline (crawler + extractor)

```bash
python run_all.py
```

1. Discovers Avature career sites and writes `data/avature_career_links.txt` and `data/all_links.txt`.
2. Loads links from `data/initial_links.txt`, `data/all_links.txt`, and `data/avature_career_links.txt`, then extracts jobs into `data/jobs.json`.

### Crawler only

```bash
python src/crawler/run_crawler.py
```

Writes career and all links to `data/`.

### Job extractor only

```bash
python src/extract/run_job_extractor.py
```

Uses existing link files in `data/` and writes `data/jobs.json`.

### Extractor with CLI options

```bash
python src/extract/job_extractor.py --links data/initial_links.txt --output data/jobs.json
python src/extract/job_extractor.py --no-rss --max-pages 200
```

## Data files

| File | Description |
|------|-------------|
| `data/initial_links.txt` | Your seed career-site URLs (one per line). Used first when present. |
| `data/avature_career_links.txt` | Career hub URLs found by the crawler. |
| `data/all_links.txt` | Career hubs + job links collected from RSS. |
| `data/jobs.json` | Extracted jobs: `job_title`, `job_description`, `application_url`, `metadata`, etc. |

## Project structure

```
avature-scraper/
├── data/                 # All output (links + jobs.json)
├── src/
│   ├── crawler/          # Career-site discovery
│   │   ├── career_crawler.py
│   │   └── run_crawler.py
│   └── extract/          # Job extraction from links
│       ├── job_extractor.py
│       └── run_job_extractor.py
├── run_all.py            # Run crawler + extractor
├── requirements.txt
└── README.md
```

## License

MIT (or your preferred license).
