import requests
import json
import csv
import time
import os
from urllib.parse import urlparse

# --- CONFIGURATION ---
INPUT_FILE = "input_urls.txt"
OUTPUT_FILE = "avature_jobs_scraped.csv"
# V2 HEADERS: Stronger camouflage
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest", # <--- CRITICAL: Tells server we want JSON
    "Origin": "https://avature.net",
    "Referer": "https://avature.net/"
}

def get_base_url(url):
    """Ensures we have the clean base domain (e.g., https://cbs.avature.net)"""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"

def scrape_site(site_url):
    """
    Reverse-Engineered Logic:
    Most Avature sites accept a POST request to /careers/SearchJobs
    with a JSON payload specifying the offset (pagination).
    """
    base_url = get_base_url(site_url)
    
    # 1. The Hidden API Endpoint
    # We found this by inspecting Network Traffic (F12) on an Avature site.
    api_url = f"{base_url}/careers/SearchJobs"
    
    jobs = []
    offset = 0
    batch_size = 50 # Avature usually allows up to 50 or 100 per request
    
    print(f"\n[*] Target: {base_url}")

    while True:
        # 2. Construct the Payload
        # This tells the server: "Give me 50 jobs, starting at index X"
        payload = {
            "jobOffset": offset,
            "jobRecordsPerPage": batch_size,
            "filters": [],
            "sort": "dateUpdated DESC" # Try to get newest first
        }

        try:
            # 3. Send the Request
            # We use POST because that's what the real website uses.
            response = requests.post(api_url, headers=HEADERS, json=payload, timeout=10)
            
            # Handle non-JSON responses (some sites might use a different URL structure)
            if response.status_code != 200:
                print(f"    -> API Error: Status {response.status_code}")
                break
                
            data = response.json()
            
            # 4. Locate the Data
            # The list of jobs is usually under 'records' or 'jobs' keys.
            results = data.get('records') or data.get('jobs') or []
            
            if not results:
                print("    -> No more jobs found (End of list).")
                break
                
            # 5. Extract & Clean Data
            for item in results:
                # Be defensive: .get() prevents crashing if a field is missing
                job = {
                    "source_url": base_url,
                    "job_id": item.get("jobId") or item.get("id"),
                    "title": item.get("title") or item.get("jobTitle"),
                    "location": item.get("location"),
                    "date_posted": item.get("dateUpdated"),
                    "apply_link": item.get("link") or f"{base_url}/Job/{item.get('jobId')}",
                    # Some descriptions are HTML, some are text. We save as-is for now.
                    "description_snippet": str(item.get("description", ""))[:100].replace("\n", " ")
                }
                jobs.append(job)

            print(f"    -> Fetched batch {offset}-{offset+len(results)} (Total: {len(jobs)})")
            
            # 6. Pagination Logic
            offset += len(results)
            
            # Safety brake: Stop after 200 jobs per site to keep the run fast for testing
            if len(jobs) >= 200:
                print("    -> Limit reached (200 jobs). Moving to next site.")
                break
                
            time.sleep(1) # Be polite to the server

        except json.JSONDecodeError:
            print("    -> Failed to parse JSON. Site might not support this API.")
            break
        except Exception as e:
            print(f"    -> Error: {e}")
            break

    return jobs

def main():
    # Load input URLs
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Error: {INPUT_FILE} not found. Run discovery.py first!")
        return

    with open(INPUT_FILE, "r") as f:
        urls = [line.strip() for line in f if line.strip()]

    all_scraped_data = []

    # Iterate through all discovered sites
    for url in urls:
        site_jobs = scrape_site(url)
        all_scraped_data.extend(site_jobs)

    # Save Results
    if all_scraped_data:
        keys = all_scraped_data[0].keys()
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(all_scraped_data)
        print(f"\n✅ SUCCESS: Scraped {len(all_scraped_data)} total jobs.")
        print(f"📂 Data saved to: {OUTPUT_FILE}")
    else:
        print("\n❌ Failed: No jobs scraped.")

if __name__ == "__main__":
    main()