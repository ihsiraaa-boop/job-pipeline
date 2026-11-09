import os
import json
import time
from datetime import datetime, timezone, timedelta

import requests

# ============================================================
# CONFIG
# ============================================================
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

MAX_MESSAGES_PER_RUN = 50   # hard cap so every run finishes
MAX_JOB_AGE_DAYS = 14       # skip jobs older than this (0 = no limit)

# Referral settings — leave unset until you are approved by a program.
REFERRAL_CODE = os.environ.get("REFERRAL_CODE", "").strip()
REFERRAL_DOMAINS = [
    d.strip().lower()
    for d in os.environ.get("REFERRAL_DOMAINS", "").split(",")
    if d.strip()
]

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

# ============================================================
# STATE (remember what we've already sent)
# ============================================================
def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(list(seen)), f)

# ============================================================
# FETCHERS
# ============================================================
def fetch_greenhouse(company):
    url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    jobs = r.json().get("jobs", [])
    return [{
        "id": f"gh_{company}_{job['id']}",
        "title": job.get("title", "Untitled"),
        "company": company.replace("-", " ").title(),
        "location": (job.get("location") or {}).get("name", "Not specified"),
        "url": job.get("absolute_url", ""),
        "date": job.get("updated_at", ""),
    } for job in jobs]

def fetch_lever(company):
    url = f"https://api.lever.co/v0/postings/{company}?mode=json"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    jobs = r.json()
    return [{
        "id": f"lv_{company}_{job['id']}",
        "title": job.get("text", "Untitled"),
        "company": company.replace("-", " ").title(),
        "location": job.get("categories", {}).get("location", "Not specified"),
        "url": job.get("hostedUrl", ""),
        "date": job.get("createdAt", ""),  # epoch ms
    } for job in jobs]

def fetch_ashby(company):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    jobs = r.json().get("jobs", [])
    return [{
        "id": f"as_{company}_{job['id']}",
        "title": job.get("title", "Untitled"),
        "company": company.replace("-", " ").title(),
        "location": job.get("location", "Not specified"),
        "url": job.get("jobUrl", ""),
        "date": job.get("publishedAt") or job.get("updatedAt", ""),
    } for job in jobs]

FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
}

# ============================================================
# DATE HELPERS (handles ISO strings and epoch ms)
# ============================================================
def parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        except Exception:
            return None
    s = str(value).strip()
    if s.isdigit():
        try:
            return datetime.fromtimestamp(int(s) / 1000, tz=timezone.utc)
        except Exception:
            return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

def is_recent(value):
    if MAX_JOB_AGE_DAYS <= 0:
        return True
    dt = parse_date(value)
    if dt is None:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_JOB_AGE_DAYS)
    return dt >= cutoff

# ============================================================
# FORMATTING + REFERRAL
# ============================================================
def build_apply_url(original_url):
    if not REFERRAL_CODE:
        return original_url
    if REFERRAL_DOMAINS:
        lower = original_url.lower()
        if not any(d in lower for d in REFERRAL_DOMAINS):
            return original_url
    sep = "&" if "?" in original_url else "?"
    return f"{original_url}{sep}ref={REFERRAL_CODE}"

def format_post(job):
    return (
        f"{job['title']}\n"
        f"{job['company']} — {job['location']}\n"
        f"\n"
        f"Apply here:\n"
        f"{build_apply_url(job['url'])}"
    )

# ============================================================
# TELEGRAM (plain text — no parse_mode)
# ============================================================
def send_telegram(text, max_retries=3):
    """Returns 'ok' on success, 'fail' on permanent failure."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": False,
        # NO parse_mode — prevents 400 "can't parse entities" errors
    }

    for attempt in range(max_retries):
        try:
            r = requests.post(url, json=payload, timeout=20)
        except Exception as e:
            print(f"Network error ({attempt + 1}/{max_retries}): {e}")
            time.sleep(3)
            continue

        if r.status_code == 200:
            return "ok"

        if r.status_code == 429:
            retry_after = 30
            try:
                retry_after = r.json().get("parameters", {}).get("retry_after", 30)
            except Exception:
                pass
            print(f"Rate limited. Sleeping {retry_after}s...")
            time.sleep(retry_after)
            continue

        # 400 and anything else — will never succeed, do not retry
        print(f"Telegram error {r.status_code}: {r.text[:200]}")
        return "fail"

    return "fail"

# ============================================================
# MAIN
# ============================================================
def main():
    seen = load_seen()
    sent = 0
    skipped_old = 0
    failed = 0

    for ats, company in COMPANIES:
        if sent >= MAX_MESSAGES_PER_RUN:
            break

        fetcher = FETCHERS.get(ats)
        if not fetcher:
            print(f"Unknown ATS '{ats}' for {company}, skipping")
            continue

        try:
            jobs = fetcher(company)
        except Exception as e:
            print(f"Fetch failed for {ats}/{company}: {e}")
            continue

        for job in jobs:
            if sent >= MAX_MESSAGES_PER_RUN:
                break
            if job["id"] in seen:
                continue
            if not is_recent(job.get("date", "")):
                seen.add(job["id"])
                skipped_old += 1
                continue

            status = send_telegram(format_post(job))
            if status == "ok":
                seen.add(job["id"])
                sent += 1
                print(f"Sent: {job['title']} ({company})")
                time.sleep(1)  # stay under Telegram rate limit
            else:
                # Permanent failure — mark seen so we don't loop forever
                seen.add(job["id"])
                failed += 1

    save_seen(seen)
    print(f"Done. sent={sent}, skipped_old={skipped_old}, failed={failed}")

if __name__ == "__main__":
    main()
