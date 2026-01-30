"""
Web crawler that discovers career websites using the Avature engine
and builds a list of all links (career site URLs and optionally job listing URLs).
"""

import time
import re
import requests
from urllib.parse import urlparse, urljoin
from pathlib import Path

# Optional: DuckDuckGo for search-based discovery
try:
    from duckduckgo_search import DDGS
    HAS_DDGS = True
except ImportError:
    HAS_DDGS = False


def discover_via_crt() -> set[str]:
    """Discover Avature domains via Certificate Transparency logs (crt.sh)."""
    print("Discovering Avature domains via Certificate Transparency (crt.sh)...")
    url = "https://crt.sh/?q=%.avature.net&output=json"
    domains = set()
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        for entry in resp.json():
            for name in entry.get("name_value", "").split("\n"):
                name = name.replace("*.", "").strip().lower()
                if name.endswith("avature.net"):
                    domains.add(name)
        print(f"  CRT: found {len(domains)} unique domains.")
    except Exception as e:
        print(f"  CRT error: {e}")
    return domains


def discover_via_duckduckgo() -> set[str]:
    """Discover Avature career sites via DuckDuckGo search."""
    if not HAS_DDGS:
        print("  DuckDuckGo: skipped (install duckduckgo-search).")
        return set()

    queries = [
        "site:avature.net careers",
        '"powered by Avature" careers',
        "inurl:avature.net/careers",
        "inurl:avature.net/jobs",
    ]
    found = set()
    with DDGS() as ddgs:
        for query in queries:
            try:
                results = ddgs.text(query, max_results=50)
                for r in results:
                    href = r.get("href", "")
                    if not href:
                        continue
                    parsed = urlparse(href)
                    base = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else ""
                    if base and "avature" in base.lower():
                        found.add(base)
                time.sleep(2)
            except Exception as e:
                print(f"  DuckDuckGo query error: {e}")
    print(f"  DuckDuckGo: found {len(found)} unique base URLs.")
    return found


def domains_to_career_urls(domains: set[str]) -> set[str]:
    """Turn domains into likely career page URLs."""
    urls = set()
    for d in domains:
        d = d.strip().lower()
        if not d or not d.endswith("avature.net"):
            continue
        # Skip obvious non-career subdomains
        skip = (
            "analytics",
            "cdn",
            "clientcertificate",
            "smtp",
            "mail",
            "sandbox",
            "uat",
            "qa",
            "integrations",
            "jarvis",
            "mobiletrust",
        )
        if any(s in d for s in skip):
            continue
        base = f"https://{d}"
        urls.add(base)
        urls.add(f"{base}/careers")
        urls.add(f"{base}/jobs")
    return urls


def validate_url(session: requests.Session, url: str, timeout: int = 8) -> bool:
    """Check if URL returns 200 OK."""
    try:
        r = session.get(url, timeout=timeout, allow_redirects=True)
        return r.status_code == 200
    except Exception:
        return False


def collect_links_from_rss(session: requests.Session, base_url: str) -> list[str]:
    """Fetch RSS feed from base URL and return list of job/listing links."""
    links = []
    parsed = urlparse(base_url)
    base_origin = f"{parsed.scheme}://{parsed.netloc}"
    rss_paths = ["/rss", "/careers/rss", "/jobs/rss", "/feed", "/careers/feed"]
    for path in rss_paths:
        url = urljoin(base_origin, path)
        try:
            r = session.get(url, timeout=8)
            if r.status_code != 200:
                continue
            text = r.text
            # Simple extraction of hrefs and <link> URLs
            for m in re.finditer(r'<(?:link|a)\s[^>]*\s(?:href|url)=["\']([^"\']+)["\']', text, re.I):
                links.append(m.group(1))
            for m in re.finditer(r'<link[^>]+href=["\']([^"\']+)["\']', text, re.I):
                links.append(m.group(1))
            # Common RSS <link> inside <item>
            for m in re.finditer(r"<link>([^<]+)</link>", text):
                links.append(m.group(1).strip())
            if links:
                break
        except Exception:
            pass
    return links


def crawl(
    output_dir: str = "data",
    validate: bool = True,
    include_job_links: bool = True,
) -> tuple[list[str], list[str]]:
    """
    Discover Avature career sites, optionally validate and collect job links.
    Returns (career_site_links, all_links).
    All output files are written inside a directory named "data".
    """
    output_path = Path(output_dir).resolve()
    if output_path.name != "data":
        output_path = output_path / "data"
    output_path.mkdir(parents=True, exist_ok=True)

    # 1) Discovery
    crt_domains = discover_via_crt()
    ddgs_bases = discover_via_duckduckgo()

    career_urls = domains_to_career_urls(crt_domains)
    career_urls.update(ddgs_bases)
    # Normalize: ensure we have https and no trailing slash for base
    normalized = set()
    for u in career_urls:
        u = u.rstrip("/")
        if not u.startswith("http"):
            u = "https://" + u
        normalized.add(u)

    # 2) Validation
    if validate:
        print("Validating career URLs...")
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
        valid_sites = []
        for url in sorted(normalized):
            if validate_url(session, url):
                valid_sites.append(url)
                print(f"  [OK] {url}")
            else:
                print(f"  [--] {url}")
        career_links = valid_sites
    else:
        career_links = sorted(normalized)

    # 3) Optionally collect job links from RSS
    all_links = list(career_links)
    if include_job_links and career_links:
        print("Collecting job links from RSS feeds...")
        if not validate:
            session = requests.Session()
            session.headers.update(
                {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )
        seen = set(career_links)
        for site in career_links:
            for link in collect_links_from_rss(session, site):
                link = link.strip()
                if link and link not in seen and "avature" in link.lower():
                    seen.add(link)
                    all_links.append(link)

    # 4) Save
    career_file = output_path / "avature_career_links.txt"
    with open(career_file, "w") as f:
        for u in career_links:
            f.write(u + "\n")
    print(f"Saved {len(career_links)} career site links to {career_file}")

    all_file = output_path / "all_links.txt"
    with open(all_file, "w") as f:
        for u in all_links:
            f.write(u + "\n")
    print(f"Saved {len(all_links)} total links to {all_file}")

    return career_links, all_links


def main():
    import argparse
    p = argparse.ArgumentParser(description="Crawl Avature career sites and collect links.")
    p.add_argument("--no-validate", action="store_true", help="Skip HTTP validation of URLs")
    p.add_argument("--sites-only", action="store_true", help="Do not fetch job links from RSS")
    p.add_argument("--output-dir", default="data", help="Output directory (default: data)")
    args = p.parse_args()
    crawl(
        output_dir=args.output_dir,
        validate=not args.no_validate,
        include_job_links=not args.sites_only,
    )


if __name__ == "__main__":
    main()
