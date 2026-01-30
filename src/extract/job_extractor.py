"""
Read career links from a file, scan each link, and extract job positions
into a single JSON file with: Job Title, Job Description, Application URL, Metadata.
"""

import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Link loading & classification
# ---------------------------------------------------------------------------

def load_links_from_file(path: str | Path) -> list[str]:
    """Load URLs from a text file (one URL per line)."""
    path = Path(path)
    if not path.exists():
        return []
    urls = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and (line.startswith("http://") or line.startswith("https://")):
                urls.append(line)
    return urls


def load_links_from_files(paths: list[str | Path]) -> list[str]:
    """Load URLs from multiple files and merge (deduplicated, order preserved)."""
    seen = set()
    merged = []
    for path in paths:
        for url in load_links_from_file(path):
            if url not in seen:
                seen.add(url)
                merged.append(url)
    return merged


def is_likely_career_hub(url: str) -> bool:
    """True if URL looks like a career hub (we should fetch RSS / listing)."""
    p = urlparse(url)
    path = (p.path or "").rstrip("/").lower()
    # Base, /careers, /jobs, or short path = hub
    if not path or path in ("", "/", "/careers", "/jobs"):
        return True
    # Deeper paths might be job pages
    if "/careers/" in path or "/jobs/" in path:
        parts = [x for x in path.split("/") if x]
        return len(parts) <= 2  # e.g. /careers or /careers/ search
    return False


def is_likely_job_page(url: str) -> bool:
    """True if URL looks like a single job or content page."""
    p = urlparse(url)
    path = (p.path or "").rstrip("/").lower()
    if not path or path in ("", "/"):
        return False
    # Blogs and non-job paths we can still try to parse as "positions"
    if "/blogs/" in path or "/blog/" in path:
        return True
    # Deep paths often job detail
    parts = [x for x in path.split("/") if x]
    return len(parts) >= 2


def is_listing_page(url: str) -> bool:
    """True if URL is a job listing/search page (many jobs on one page), not a single job detail."""
    p = urlparse(url)
    path = (p.path or "").rstrip("/").lower()
    if not path:
        return False
    # SearchJobs, /careers, /jobs without a job ID = listing page
    if "searchjobs" in path and "/jobdetail" not in path:
        return True
    parts = [x for x in path.split("/") if x]
    # /careers or /jobs with 1–2 segments only (e.g. /careers, /en_US/careers, /careers/SearchJobs)
    if len(parts) <= 2 and ("careers" in path or "jobs" in path):
        return True
    if path.endswith("/careers") or path.endswith("/jobs"):
        return True
    return False


def extract_job_links_from_listing(soup: BeautifulSoup, base_url: str, netloc: str) -> list[tuple[str, str]]:
    """
    Parse listing page HTML and return list of (job_url, title_text) for each job link.
    Avature sites often use JobDetail, or links with job ID in path.
    """
    parsed_base = urlparse(base_url)
    base_origin = f"{parsed_base.scheme}://{parsed_base.netloc}"
    seen_urls: set[str] = set()
    results: list[tuple[str, str]] = []

    # Selectors that often wrap a single job row/card with a link to the job
    for a in soup.select('a[href]'):
        href = a.get("href")
        if not href or not href.strip():
            continue
        full_url = urljoin(base_url, href)
        try:
            p = urlparse(full_url)
        except Exception:
            continue
        if (p.netloc or "").lower() != netloc.lower():
            continue
        path = (p.path or "").lower()
        query = (p.query or "").lower()
        # Skip same page, search form, or non-job links
        if full_url == base_url or full_url.rstrip("/") == base_url.rstrip("/"):
            continue
        if "searchjobs" in path and "/jobdetail" not in path and "jobid" not in query and path.rstrip("/").endswith("searchjobs"):
            continue
        # Job detail links: JobDetail in path/query, or SearchJobs/123, or /careers/.../123
        is_job_link = (
            "jobdetail" in path or "jobid" in query
            or ("searchjobs" in path and path.count("/") >= 3)  # e.g. /careers/SearchJobs/123
            or ("careers" in path and any(seg.isdigit() for seg in path.split("/")) and len(path.split("/")) >= 4)
        )
        if not is_job_link:
            # Also accept any same-domain link that looks like a detail (has extra path segment)
            base_path = (parsed_base.path or "").rstrip("/")
            if path != base_path and path.startswith((base_path.split("searchjobs")[0] or base_path).lower()):
                extra = path[len(base_path):].strip("/")
                if extra and (extra.isdigit() or "/" in extra):
                    is_job_link = True
        if not is_job_link:
            continue
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        title = html_to_clean_text(a).strip() or "Job"
        if len(title) > 300:
            title = title[:300] + "..."
        results.append((full_url, title))

    # Fallback: find links by common Avature class names / structure
    if not results:
        for block in soup.select("[class*='job'], [class*='result'], [class*='position'], [data-job-id]"):
            link = block.select_one("a[href*='JobDetail'], a[href*='SearchJobs']")
            if not link:
                link = block.select_one("a[href]")
            if link:
                href = link.get("href")
                if not href:
                    continue
                full_url = urljoin(base_url, href)
                p = urlparse(full_url)
                if (p.netloc or "").lower() != netloc.lower():
                    continue
                if full_url in seen_urls:
                    continue
                path = (p.path or "").lower()
                if "jobdetail" in path or ("searchjobs" in path and len(path.split("/")) >= 4):
                    seen_urls.add(full_url)
                    title = html_to_clean_text(block).strip() or html_to_clean_text(link).strip() or "Job"
                    if len(title) > 400:
                        title = title[:400] + "..."
                    results.append((full_url, title))

    return results


# ---------------------------------------------------------------------------
# RSS parsing
# ---------------------------------------------------------------------------

# Patterns that indicate an RSS item is a blog/marketing post, not a job
RSS_NON_JOB_PATH_PATTERNS = (
    "/blogs/",
    "/blog/",
    "avatureupfront",
    "hr-trends",
    "test-cookies",
)


def is_likely_job_posting(application_url: str, job_title: str, source_feed: str) -> bool:
    """
    Return True only if this RSS item looks like a real job posting.
    Excludes vendor blog, marketing, and non-job content.
    """
    if not application_url:
        return False
    purl = urlparse(application_url)
    path = (purl.path or "").lower()
    netloc = (purl.netloc or "").lower()
    title = (job_title or "").lower()

    # Exclude vendor blog/marketing (www.avature.net, avature.net)
    if netloc in ("www.avature.net", "avature.net"):
        if "/blogs/" in path or "/blog/" in path or "avatureupfront" in path or "hr-trends" in path:
            return False
        # Vendor domain with no clear job path = likely blog/content
        if "/careers/" not in path and "/jobs/" not in path and "searchjobs" not in path:
            return False

    # Exclude known non-job path patterns
    for pattern in RSS_NON_JOB_PATH_PATTERNS:
        if pattern in path or pattern in title:
            return False

    # Include: Avature career subdomains (e.g. bloomberg.avature.net) with job-like paths
    if ".avature.net" in netloc and netloc not in ("www.avature.net", "avature.net"):
        if "/careers" in path or "/jobs" in path or "searchjobs" in path or "careers" in path or "jobs" in path:
            return True

    # Include: URL has clear job listing path
    if "/careers/" in path or "/jobs/" in path or "searchjobs" in path:
        return True
    if path.endswith("/careers") or path.endswith("/jobs") or "/careers" in path or "/jobs" in path:
        return True

    # Exclude everything else from RSS (conservative: only accept job-like URLs)
    return False


def _text(el) -> str:
    if el is None:
        return ""
    return (el.text or "").strip() + "".join((ET.tostring(e, encoding="unicode", method="text") for e in el)).strip()


def fetch_rss_jobs(session: requests.Session, base_url: str) -> list[dict]:
    """Fetch RSS from common paths and return list of job dicts (title, description, application_url, metadata)."""
    jobs = []
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    netloc = parsed.netloc or ""

    for path in ["/rss", "/careers/rss", "/jobs/rss", "/feed", "/careers/feed", "/jobs/feed"]:
        url = urljoin(origin, path)
        try:
            r = session.get(url, timeout=12)
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.content)
            # Handle default ns
            def find_all(node, tag):
                if "}" in tag:
                    return node.findall(f".//{tag}")
                return node.findall(f".//{{*}}{tag}") or node.findall(f".//{tag}")

            for item in find_all(root, "item"):
                title = _text(item.find("title") or item.find("{*}title"))
                link = _text(item.find("link") or item.find("{*}link"))
                if not link and item.find("link") is not None:
                    link = (item.find("link").text or "").strip()
                desc_el = item.find("description") or item.find("{*}description")
                description = _text(desc_el) if desc_el is not None else ""
                if not description and desc_el is not None and desc_el.text:
                    description = (desc_el.text or "").strip()
                pub = _text(item.find("pubDate") or item.find("{*}pubDate"))
                guid = _text(item.find("guid") or item.find("{*}guid"))

                if not title and not link:
                    continue
                if not link and guid and (guid.startswith("http") or guid.startswith("//")):
                    link = guid if guid.startswith("http") else parsed.scheme + ":" + guid
                if not link:
                    continue

                # Only include items that look like actual job postings (exclude blog/marketing)
                if not is_likely_job_posting(link, title, url):
                    continue

                job = {
                    "job_title": title or "Untitled",
                    "job_description": description,
                    "application_url": link,
                    "metadata": {
                        "date_posted": pub or None,
                        "job_id": guid or None,
                        "source_feed": url,
                    },
                    "source_site": netloc,
                    "source_url": url,
                }
                jobs.append(job)
            if jobs:
                break
        except ET.ParseError:
            pass
        except Exception:
            pass
        time.sleep(0.3)
    return jobs


# ---------------------------------------------------------------------------
# HTML parsing (job detail pages)
# ---------------------------------------------------------------------------

def html_to_clean_text(soup_tag) -> str:
    """Extract clean text from a BeautifulSoup node."""
    if soup_tag is None:
        return ""
    text = soup_tag.get_text(separator="\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_job_from_html(session: requests.Session, url: str) -> dict | None:
    """Fetch a URL and try to extract a single job (title, description, application_url, metadata)."""
    try:
        r = session.get(url, timeout=12)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:
        return None

    parsed = urlparse(url)
    netloc = parsed.netloc or ""
    title = ""
    description = ""
    application_url = url
    metadata = {"source_page": url}

    # Title: h1, .job-title, .position-title, [data-job-title], title tag
    for sel in ["h1", ".job-title", ".position-title", "[data-job-title]", ".job-header h1", ".page-title"]:
        el = soup.select_one(sel)
        if el:
            title = html_to_clean_text(el)
            break
    if not title and soup.title:
        title = (soup.title.string or "").strip()

    # Description: .job-description, .description, .job-details, article, .content, main
    for sel in [
        ".job-description",
        ".job-description .content",
        ".description",
        ".job-details",
        "article",
        ".job-content",
        ".position-description",
        "[data-job-description]",
        "main .content",
        "main",
        ".content",
    ]:
        el = soup.select_one(sel)
        if el:
            raw = str(el) if "job_description_raw" not in dir() else el.decode_contents()
            description = html_to_clean_text(el)
            if len(description) > 100:
                break
    if not description:
        body = soup.find("body")
        if body:
            description = html_to_clean_text(body)[:15000]

    # Application URL: apply button/link
    for sel in [
        'a[href*="apply"]',
        'a[href*="Apply"]',
        'button a[href^="http"]',
        '.apply-button a',
        '.apply-btn a',
        'a.btn-apply[href]',
        '[data-apply-url]',
    ]:
        try:
            el = soup.select_one(sel)
        except Exception:
            el = None
        if el:
            href = el.get("href")
            if href:
                application_url = urljoin(url, href)
                break

    # Metadata: location, date posted
    for sel in [".location", ".job-location", "[data-location]", ".location-value", ".posted-date", ".date-posted"]:
        el = soup.select_one(sel)
        if el:
            text = html_to_clean_text(el)
            if "location" in sel.lower() or "location" in str(el.get("class", [])):
                metadata["location"] = text
            elif "date" in sel.lower() or "posted" in sel.lower():
                metadata["date_posted"] = text

    if not title and not description:
        return None

    return {
        "job_title": title or "Untitled",
        "job_description": description,
        "application_url": application_url,
        "metadata": metadata,
        "source_site": netloc,
        "source_url": url,
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_extraction(
    links_file: str | Path | None = None,
    links_files: list[str | Path] | None = None,
    output_file: str | Path = "data/jobs.json",
    fetch_rss: bool = True,
    fetch_job_pages: bool = True,
    max_job_pages: int = 500,
) -> list[dict]:
    """
    Load links from file(s), extract jobs from RSS and optionally from job pages, write JSON.
    If links_files is provided, load from all those files (merged). Otherwise use links_file.
    Returns list of all job dicts.
    """
    if links_files:
        links = load_links_from_files(links_files)
    else:
        links = load_links_from_file(links_file or "data/avature_career_links.txt")
    if not links:
        print("No links found in the given file(s).")
        return []

    print(f"Loaded {len(links)} links")

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )

    all_jobs: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()  # (source_site, application_url) for dedup

    def add_job(job: dict) -> None:
        # Only add items that look like actual job postings (no blog/marketing)
        app_url = job.get("application_url", "")
        if app_url and ("/blogs/" in app_url or "/blog/" in app_url):
            return
        if not is_likely_job_posting(app_url, job.get("job_title", ""), job.get("source_url", "")):
            # Allow HTML-extracted jobs from career subdomains even if URL pattern is generic
            purl = urlparse(app_url)
            netloc = (purl.netloc or "").lower()
            if netloc in ("www.avature.net", "avature.net"):
                return
        key = (job.get("source_site", ""), app_url)
        if key in seen_keys:
            return
        seen_keys.add(key)
        # Normalize for JSON
        job["extracted_at"] = datetime.utcnow().isoformat() + "Z"
        all_jobs.append(job)

    # 1) Career hubs: fetch RSS
    hubs = [u for u in links if is_likely_career_hub(u)]
    if fetch_rss and hubs:
        print(f"Fetching RSS from {len(hubs)} career hub(s)...")
        for url in hubs:
            try:
                jobs = fetch_rss_jobs(session, url)
                for j in jobs:
                    add_job(j)
                if jobs:
                    print(f"  RSS: {url} -> {len(jobs)} jobs")
            except Exception as e:
                print(f"  RSS error {url}: {e}")
            time.sleep(0.5)

    # 2) Job-like pages: listing pages → extract all job links, then fetch each; single pages → fetch once
    job_page_urls = [u for u in links if is_likely_job_page(u)]
    if fetch_job_pages and job_page_urls:
        to_fetch = job_page_urls[:max_job_pages]
        print(f"Fetching {len(to_fetch)} job/page URL(s) (listing pages → multiple jobs each)...")
        for url in to_fetch:
            try:
                parsed = urlparse(url)
                netloc = parsed.netloc or ""
                if is_listing_page(url):
                    # Listing page: get HTML, find all job links, fetch each job detail
                    r = session.get(url, timeout=12)
                    if r.status_code != 200:
                        time.sleep(0.4)
                        continue
                    soup = BeautifulSoup(r.text, "html.parser")
                    job_links = extract_job_links_from_listing(soup, url, netloc)
                    if job_links:
                        for job_url, card_title in job_links[:100]:  # cap per listing to avoid runaway
                            try:
                                job = extract_job_from_html(session, job_url)
                                if job:
                                    if not job.get("job_title") or job.get("job_title") == "Untitled":
                                        job["job_title"] = card_title
                                    add_job(job)
                            except Exception:
                                pass
                            time.sleep(0.35)
                    else:
                        # No job links found (e.g. JS-rendered): treat whole page as one entry
                        job = extract_job_from_html(session, url)
                        if job:
                            add_job(job)
                    time.sleep(0.4)
                else:
                    job = extract_job_from_html(session, url)
                    if job:
                        add_job(job)
                    time.sleep(0.4)
            except Exception:
                pass

    # 3) Also discover job URLs from RSS and optionally fetch each (for richer data)
    if fetch_rss and hubs and fetch_job_pages:
        rss_job_urls = [j["application_url"] for j in all_jobs if j.get("application_url")]
        already = {u for u in job_page_urls}
        to_enrich = [u for u in rss_job_urls if u not in already][:max_job_pages]
        print(f"Enriching {len(to_enrich)} job URLs from RSS...")
        for url in to_enrich:
            try:
                job = extract_job_from_html(session, url)
                if job and (job.get("job_description") or job.get("metadata")):
                    # Prefer enriched version: same application_url, merge metadata
                    key = (job.get("source_site", ""), job.get("application_url", ""))
                    if key in seen_keys:
                        for i, existing in enumerate(all_jobs):
                            if (existing.get("source_site"), existing.get("application_url")) == key:
                                if job.get("job_description") and len(job["job_description"]) > len(existing.get("job_description", "")):
                                    existing["job_description"] = job["job_description"]
                                if job.get("metadata"):
                                    existing["metadata"] = {**existing.get("metadata", {}), **job["metadata"]}
                                break
                    else:
                        add_job(job)
            except Exception:
                pass
            time.sleep(0.4)

    # 4) Write single JSON file (always under a directory named "data")
    output_path = Path(output_file).resolve()
    if output_path.parent.name != "data":
        output_path = output_path.parent / "data" / output_path.name
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(all_jobs)} jobs to {output_path}")
    return all_jobs


def main():
    import argparse
    p = argparse.ArgumentParser(description="Extract job positions from career links into a single JSON file.")
    p.add_argument("--links", default="data/avature_career_links.txt", help="Input file with one URL per line")
    p.add_argument("--initial-links", action="store_true", help="Use data/initial_links.txt (and merge with other data link files)")
    p.add_argument("--output", default="data/jobs.json", help="Output JSON file")
    p.add_argument("--no-rss", action="store_true", help="Skip RSS fetching")
    p.add_argument("--no-pages", action="store_true", help="Skip fetching individual job pages")
    p.add_argument("--max-pages", type=int, default=500, help="Max job pages to fetch (default 500)")
    args = p.parse_args()
    links_files = None
    if args.initial_links:
        links_files = ["data/initial_links.txt", "data/all_links.txt", "data/avature_career_links.txt"]
    run_extraction(
        links_file=args.links if not links_files else None,
        links_files=links_files,
        output_file=args.output,
        fetch_rss=not args.no_rss,
        fetch_job_pages=not args.no_pages,
        max_job_pages=args.max_pages,
    )


if __name__ == "__main__":
    main()
