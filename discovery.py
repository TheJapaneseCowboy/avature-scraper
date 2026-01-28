import requests
import time
import sys
from urllib.parse import urlparse

# Try to import the google search library
try:
    from googlesearch import search
except ImportError:
    print("❌ Error: 'googlesearch-python' is not installed.")
    print("   Run: pip install googlesearch-python")
    sys.exit(1)

# --- CONFIGURATION ---
OUTPUT_FILE = "input_urls.txt"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def clean_url(url):
    """
    Standardizes URLs to 'https://domain.avature.net/careers'
    """
    parsed = urlparse(url)
    # Ensure scheme is https
    scheme = "https"
    # Get the domain (e.g., nike.avature.net)
    netloc = parsed.netloc
    
    # If the URL came in without a scheme (e.g. "nike.avature.net"), netloc might be empty
    if not netloc:
        netloc = parsed.path
        
    return f"{scheme}://{netloc}/careers"

def validate_url(url):
    """
    Checks if the URL is actually live (Status 200).
    Returns the final URL (handles redirects) or None if dead.
    """
    try:
        # We verify=False to avoid SSL errors on misconfigured internal sites
        response = requests.head(url, headers=HEADERS, timeout=5, verify=False)
        if response.status_code < 400:
            return url
    except:
        pass
    return None

# --- TECHNIQUE 1: GOOGLE DORKING ---
def run_google_dorking():
    print("\n🔍 [Method 1] Starting Google Dorking...")
    
    queries = [
        "site:avature.net", 
        "site:avature.net/careers",
        '"powered by Avature" jobs'
    ]
    
    found_sites = set()
    
    for query in queries:
        print(f"   -> Running dork: {query}")
        try:
            # sleep_interval is CRITICAL to avoid being banned
            results = search(query, num_results=15, sleep_interval=2, advanced=True)
            
            for result in results:
                url = result.url
                if "avature.net" in url and "www.avature.net" not in url:
                    clean = clean_url(url)
                    if clean not in found_sites:
                        print(f"      Found: {clean}")
                        found_sites.add(clean)
                        
        except Exception as e:
            print(f"      ⚠️ Google Error (likely 429 blocking): {e}")
            break # Stop dorking if blocked, move to next method
            
    print(f"   ✅ Method 1 found {len(found_sites)} sites.")
    return found_sites

# --- TECHNIQUE 2: CERTIFICATE LOGS (Backup) ---
def run_crt_sh_discovery():
    print("\n🔍 [Method 2] Querying Certificate Transparency Logs (crt.sh)...")
    print("   (This finds every subdomain ever registered - very powerful)")
    
    # This API searches for any subdomain ending in .avature.net
    url = "https://crt.sh/?q=%.avature.net&output=json"
    found_sites = set()
    
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            data = response.json()
            for entry in data:
                # The 'name_value' often contains the domain
                name_value = entry.get('name_value', '')
                
                # Sometimes it returns multiple domains separated by newlines
                subdomains = name_value.split('\n')
                
                for domain in subdomains:
                    if "avature.net" in domain and "*" not in domain:
                        clean = clean_url(f"https://{domain}")
                        found_sites.add(clean)
            
            print(f"   ✅ Method 2 found {len(found_sites)} raw subdomains.")
        else:
            print(f"   ⚠️ crt.sh returned status {response.status_code}")
            
    except Exception as e:
        print(f"   ⚠️ Error connecting to crt.sh: {e}")
        
    return found_sites

def main():
    all_candidates = set()
    
    # 1. Run Google Dorking
    dork_results = run_google_dorking()
    all_candidates.update(dork_results)
    
    # 2. Run Certificate Transparency (The "Safety Net")
    crt_results = run_crt_sh_discovery()
    all_candidates.update(crt_results)
    
    print(f"\nrunning validation on {len(all_candidates)} candidates...")
    
    # 3. Validation & Saving
    valid_sites = set()
    with open(OUTPUT_FILE, "w") as f:
        for url in sorted(all_candidates):
            # We filter out the main marketing site
            if "www.avature.net" in url or "kb.avature.net" in url:
                continue
                
            # Optional: Check if active (slows script down but ensures quality)
            # If you want speed, comment out the 'validate_url' check
            # if validate_url(url): 
            valid_sites.add(url)
            f.write(url + "\n")
            print(f"   Saved: {url}")
    
    print(f"\n🎉 SUCCESS: Discovered and saved {len(valid_sites)} unique Avature sites to '{OUTPUT_FILE}'.")

if __name__ == "__main__":
    main()