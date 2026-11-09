import os
import json
import requests

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# ============================================================
# ADD YOUR COMPANIES HERE
# Format: ("ats_name", "company_slug")
# ats_name must be one of: "greenhouse", "lever", "ashby"
# ============================================================
COMPANIES = [
    # --- India-focused product companies & startups ---
    ("greenhouse", "razorpay"),
    ("greenhouse", "cred"),
    ("greenhouse", "groww"),
    ("greenhouse", "paytm"),
    ("greenhouse", "meesho"),
    ("greenhouse", "zeta"),
    ("greenhouse", "inmobi"),
    ("greenhouse", "sarvamai"),
    ("greenhouse", "freshworks"),
    ("greenhouse", "zscaler"),
    ("lever", "swiggy"),
    ("lever", "meesho"),
    ("lever", "cred"),

    # --- Global tech & AI (Greenhouse) ---
    ("greenhouse", "stripe"),
    ("greenhouse", "databricks"),
    ("greenhouse", "mongodb"),
    ("greenhouse", "okta"),
    ("greenhouse", "gitlab"),
    ("greenhouse", "huggingface"),
    ("greenhouse", "airbnb"),
    ("greenhouse", "coinbase"),
    ("greenhouse", "robinhood"),
    ("greenhouse", "doordash"),
    ("greenhouse", "discord"),
    ("greenhouse", "figma"),
    ("greenhouse", "notion"),
    ("greenhouse", "vercel"),
    ("greenhouse", "asana"),
    ("greenhouse", "brex"),
    ("greenhouse", "ramp"),
    ("greenhouse", "plaid"),
    ("greenhouse", "rippling"),
    ("greenhouse", "gusto"),
    ("greenhouse", "anthropic"),
    ("greenhouse", "openai"),
    ("greenhouse", "netflix"),
    ("greenhouse", "spotify"),

    # --- Global tech & AI (Lever) ---
    ("lever", "palantir"),
    ("lever", "whoop"),
    ("lever", "gopuff"),
    ("lever", "zoox"),
    ("lever", "spotify"),
    ("lever", "netflix"),

    # --- Global tech & AI (Ashby) ---
    ("ashby", "elevenlabs"),
    ("ashby", "mercury"),
    ("ashby", "sierra"),
    ("ashby", "synthesia"),
    ("ashby", "linear"),
    ("ashby", "posthog"),
    ("ashby", "openai"),
    ("ashby", "notion"),
    ("ashby", "vercel"),
    ("ashby", "supabase"),
    ("ashby", "cursor"),
    ("ashby", "deel"),
    ("ashby", "ramp"),
    ("ashby", "plaid"),
    ("ashby", "mistral.ai"),
]
SEEN_FILE = "seen_jobs.json"

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(list(seen)), f)

def fetch_greenhouse(company):
    url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    jobs = r.json().get("jobs", [])
    results = []
    for job in jobs:
        results.append({
            "id": f"gh_{company}_{job['id']}",
            "title": job.get("title", "Untitled"),
            "company": company.replace("-", " ").title(),
            "location": (job.get("location") or {}).get("name", "Not specified"),
            "url": job.get("absolute_url", ""),
        })
    return results

def fetch_lever(company):
    url = f"https://api.lever.co/v0/postings/{company}?mode=json"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    jobs = r.json()
    results = []
    for job in jobs:
        results.append({
            "id": f"lv_{company}_{job['id']}",
            "title": job.get("text", "Untitled"),
            "company": company.replace("-", " ").title(),
            "location": job.get("categories", {}).get("location", "Not specified"),
            "url": job.get("hostedUrl", ""),
        })
    return results

def fetch_ashby(company):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    jobs = r.json().get("jobs", [])
    results = []
    for job in jobs:
        results.append({
            "id": f"as_{company}_{job['id']}",
            "title": job.get("title", "Untitled"),
            "company": company.replace("-", " ").title(),
            "location": job.get("location", "Not specified"),
            "url": job.get("jobUrl", ""),
        })
    return results

def format_post(job):
    return (
        f"*{job['title']}*\n"
        f"{job['company']} — {job['location']}\n\n"
        f"Apply here:\n{job['url']}"
    )

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()

def main():
    seen = load_seen()
    fetch_map = {
        "greenhouse": fetch_greenhouse,
        "lever": fetch_lever,
        "ashby": fetch_ashby,
    }

    for ats, company in COMPANIES:
        try:
            jobs = fetch_map[ats](company)
        except Exception as e:
            print(f"Fetch failed for {ats}/{company}: {e}")
            continue

        for job in jobs:
            if job["id"] in seen:
                continue
            try:
                send_telegram(format_post(job))
                seen.add(job["id"])
                print(f"Sent: {job['title']} ({company})")
            except Exception as e:
                print(f"Send failed for {job['id']}: {e}")

    save_seen(seen)

if __name__ == "__main__":
    main()
