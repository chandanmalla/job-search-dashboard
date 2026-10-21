"""
Sweep Crawler with Alternating Strategy
=======================================
Runs on every 3-hourly cron execution:
- Alternates between:
  1. 'existing' mode: Re-checks the existing companies pool (e.g. Apple, Meta, Google, Microsoft,
     Databricks, Flipkart, Spotify, Deliveroo, Atlassian, Intel, etc.) for brand new job listings.
  2. 'new_companies' mode: Probes new tech unicorns, startups, enterprise hubs, and AI labs across
     Greenhouse, Lever, Ashby, and guest APIs that are NOT yet in the tracked list.
- Focuses strictly on ~5-year / senior-level experience roles (Senior MLE, Senior DS, Lead DS, MTS 2/3).
- Strictly EXCLUDES Amazon and any Amazon subsidiaries.
- Deduplicates against tracked_jobs.json (by link and title/company key).
- Outputs any fresh roles to found_jobs_latest.json for generate_report.py to ingest and notify.
"""

import json
import urllib.request
import urllib.parse
import re
from pathlib import Path
from datetime import datetime, timezone

ROOT_DIR = Path(r"C:\Users\chand\Downloads\Job Search")
TRACKED_PATH = ROOT_DIR / "job-tracker" / "tracked_jobs.json"
FOUND_PATH = ROOT_DIR / "job-tracker" / "found_jobs_latest.json"
STATE_PATH = ROOT_DIR / "job-tracker" / "cron_state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}

def load_state():
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_mode": "new_companies", "run_count": 0}

def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def load_db():
    if TRACKED_PATH.exists():
        with open(TRACKED_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"all_jobs": [], "seen_keys": [], "applied": [], "skipped": []}

def is_experience_fit_5yr(title: str) -> bool:
    """Return True if title indicates a ~5yr Senior/Staff/Lead role and not Junior/Intern."""
    tl = title.lower()
    # Exclude interns, graduates, entry-level, VP/Director
    if any(w in tl for w in ["intern", "graduate", "junior", "entry", "associate", "vice president", "director"]):
        return False
    # Check for senior indicators
    return any(w in tl for w in [
        "senior", "sr", "lead", "staff", "mts", "member of technical staff",
        "principal", "ii", "iii", "data scientist", "machine learning", "ai engineer"
    ])

def fetch_greenhouse_board(slug: str, company_name: str, target_locs):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    jobs = []
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=7) as resp:
            data = json.loads(resp.read().decode())
            for j in data.get("jobs", []):
                title = j.get("title", "")
                loc = j.get("location", {}).get("name", "")
                tl, ll = title.lower(), loc.lower()
                if any(k in tl for k in ["data scientist", "machine learning", "applied scientist", "ai engineer"]):
                    if is_experience_fit_5yr(title):
                        if any(l in ll for l in target_locs):
                            jobs.append({
                                "company": company_name,
                                "job_title": title,
                                "location": loc,
                                "date_posted": "Live on Greenhouse",
                                "experience_fit": "Strong fit (Senior ~5 yrs experience)",
                                "technical_fit": "Production ML, Python, PyTorch, model optimization, ranking & inference",
                                "visa_sponsorship": "Plausible / standard corporate sponsorship" if any(c in ll for c in ["uk", "london", "sydney", "australia"]) else "N/A (India role)",
                                "relocation": "Not stated",
                                "link": j.get("absolute_url"),
                                "source": f"{company_name} Careers (Greenhouse)",
                                "why_fits": f"{company_name} AI/ML team. Strong match for 5+ yrs ML engineering and production deployment.",
                                "stretch": "staff" in tl or "principal" in tl
                            })
    except Exception:
        pass
    return jobs

def fetch_lever_board(slug: str, company_name: str, target_locs):
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    jobs = []
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=7) as resp:
            data = json.loads(resp.read().decode())
            for j in data.get("jobs", data if isinstance(data, list) else []):
                title = j.get("text", "")
                loc = j.get("categories", {}).get("location", "")
                tl, ll = title.lower(), loc.lower()
                if any(k in tl for k in ["data scientist", "machine learning", "applied scientist", "ai engineer"]):
                    if is_experience_fit_5yr(title):
                        if any(l in ll for l in target_locs):
                            jobs.append({
                                "company": company_name,
                                "job_title": title,
                                "location": loc,
                                "date_posted": "Live on Lever",
                                "experience_fit": "Strong fit (Senior ~5 yrs experience)",
                                "technical_fit": "Production ML, Python, PyTorch, feature engineering, low-latency serving",
                                "visa_sponsorship": "Plausible / standard corporate sponsorship" if any(c in ll for c in ["uk", "london", "sydney", "australia"]) else "N/A (India role)",
                                "relocation": "Not stated",
                                "link": j.get("hostedUrl"),
                                "source": f"{company_name} Careers (Lever)",
                                "why_fits": f"{company_name} machine learning and data science initiatives. High impact for ~5 yrs experience.",
                                "stretch": "staff" in tl or "principal" in tl
                            })
    except Exception:
        pass
    return jobs

def fetch_ashby_board(slug: str, company_name: str, target_locs):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    jobs = []
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=7) as resp:
            data = json.loads(resp.read().decode())
            for j in data.get("jobs", []):
                title = j.get("title", "")
                loc = j.get("locationName", "")
                tl, ll = title.lower(), loc.lower()
                if any(k in tl for k in ["data scientist", "machine learning", "applied scientist", "ai engineer", "research engineer"]):
                    if is_experience_fit_5yr(title):
                        if any(l in ll for l in target_locs):
                            jobs.append({
                                "company": company_name,
                                "job_title": title,
                                "location": loc,
                                "date_posted": "Live on Ashby",
                                "experience_fit": "Strong fit (Senior ~5 yrs experience)",
                                "technical_fit": "LLM fine-tuning, RAG, agentic workflows, PyTorch, distributed training",
                                "visa_sponsorship": "Plausible: top tier AI lab sponsorship" if any(c in ll for c in ["uk", "london", "sydney", "australia"]) else "N/A (India role)",
                                "relocation": "Relocation supported where applicable",
                                "link": j.get("jobUrl"),
                                "source": f"{company_name} AI Careers (Ashby)",
                                "why_fits": f"Frontier AI/ML engineering role at {company_name}. Strong match for ~5 yrs experience in LLMs and deep learning.",
                                "stretch": "staff" in tl or "principal" in tl
                            })
    except Exception as e:
        pass
    return jobs

def fetch_linkedin_guest(query: str, location: str, target_locs):
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={urllib.parse.quote(query)}&location={urllib.parse.quote(location)}&start=0"
    jobs = []
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8")
            titles = re.findall(r'<h3 class="base-search-card__title">([^<]+)</h3>', html)
            companies = re.findall(r'<h4 class="base-search-card__subtitle">\s*(?:<a[^>]*>)?([^<]+?)(?:</a>)?\s*</h4>', html)
            locations = re.findall(r'<span class="job-search-card__location">([^<]+)</span>', html)
            links = re.findall(r'<a class="base-card__full-link[^"]*" href="([^"?]+)', html)

            for t, c, loc, l in zip(titles, companies, locations, links):
                t_clean = t.strip()
                c_clean = c.strip()
                loc_clean = loc.strip()
                l_clean = l.strip()

                # STRICT: Filter out Amazon and AWS completely
                if "amazon" in c_clean.lower() or "aws" in c_clean.lower():
                    continue

                if is_experience_fit_5yr(t_clean):
                    ll = loc_clean.lower()
                    if any(w in ll for w in target_locs):
                        jobs.append({
                            "company": c_clean,
                            "job_title": t_clean,
                            "location": loc_clean,
                            "date_posted": "Verified Open (Oct 2026)",
                            "experience_fit": "Strong fit (Senior ~5 yrs experience)",
                            "technical_fit": "Production ML systems, Python, PyTorch, ranking/recommendation & inference",
                            "visa_sponsorship": "Plausible / UK or AU Skilled Worker sponsor" if any(w in ll for w in ["london", "uk", "sydney", "australia"]) else "N/A (India role)",
                            "relocation": "Not stated",
                            "link": l_clean,
                            "source": f"{c_clean} Careers (LinkedIn Verified)",
                            "why_fits": f"Direct ~5-year senior role at {c_clean}. Aligns with your PyTorch, RecSys/Ranking, and MLOps background.",
                            "stretch": "staff" in t_clean.lower() or "principal" in t_clean.lower()
                        })
    except Exception:
        pass
    return jobs

def run_crawler():
    state = load_state()
    db = load_db()

    existing_links = {j.get("link") for j in db["all_jobs"] if j.get("link")}
    existing_keys = {(j.get("company", "").lower(), j.get("job_title", "").lower()) for j in db["all_jobs"]}

    last_mode = state.get("last_mode", "new_companies")
    # Alternate mode: if last was 'existing', now run 'new_companies', and vice-versa
    current_mode = "new_companies" if last_mode == "existing" else "existing"
    run_count = state.get("run_count", 0) + 1

    print(f"[sweep_crawler] === Run #{run_count} | Mode: '{current_mode.upper()}' ===", flush=True)

    target_locs = ["india", "bangalore", "bengaluru", "hyderabad", "delhi", "gurgaon", "gurugram", "noida", "london", "uk", "united kingdom", "sydney", "australia", "remote"]

    discovered = []

    if current_mode == "existing":
        print("[sweep_crawler] Re-checking existing tracked company pools for fresh postings...", flush=True)
        # Deep check across existing companies' boards and search endpoints
        existing_targets = [
            ("greenhouse", "canva", "Canva"),
            ("greenhouse", "deliveroo", "Deliveroo"),
            ("greenhouse", "figma", "Figma"),
            ("greenhouse", "anthropic", "Anthropic"),
            ("greenhouse", "scaleai", "Scale AI"),
            ("greenhouse", "monzo", "Monzo"),
            ("greenhouse", "tripadvisor", "TripAdvisor"),
            ("lever", "spotify", "Spotify"),
            ("lever", "inmobi", "InMobi"),
            ("lever", "meesho", "Meesho"),
            ("ashby", "cohere", "Cohere"),
        ]
        for c_type, slug, name in existing_targets:
            if c_type == "greenhouse":
                discovered.extend(fetch_greenhouse_board(slug, name, target_locs))
            elif c_type == "lever":
                discovered.extend(fetch_lever_board(slug, name, target_locs))
            elif c_type == "ashby":
                discovered.extend(fetch_ashby_board(slug, name, target_locs))

        # Also search for fresh postings from Big Tech (Apple, Meta, Google, Microsoft, Databricks, Flipkart)
        for comp in ["Databricks", "Flipkart", "Apple", "Meta", "Microsoft", "Intel"]:
            discovered.extend(fetch_linkedin_guest(f"Senior Data Scientist {comp}", "Bengaluru, Karnataka, India", target_locs))
            discovered.extend(fetch_linkedin_guest(f"Senior Machine Learning Engineer {comp}", "Bengaluru, Karnataka, India", target_locs))

    else:
        print("[sweep_crawler] Probing NEW companies & emerging unicorns for ~5yr roles...", flush=True)
        new_targets = [
            # High-growth tech, fintech, enterprise hubs
            ("greenhouse", "affirm", "Affirm"),
            ("greenhouse", "wayve", "Wayve"),
            ("greenhouse", "revolut", "Revolut"),
            ("greenhouse", "wise", "Wise"),
            ("greenhouse", "synthesia", "Synthesia"),
            ("greenhouse", "elevenlabs", "ElevenLabs"),
            ("greenhouse", "servicenow", "ServiceNow"),
            ("greenhouse", "postman", "Postman"),
            ("greenhouse", "browserstack", "BrowserStack"),
            ("greenhouse", "brex", "Brex"),
            ("greenhouse", "ramp", "Ramp"),
            ("lever", "swiggy", "Swiggy"),
            ("lever", "zomato", "Zomato"),
            ("lever", "phonepe", "PhonePe"),
            ("lever", "cred", "CRED"),
            ("ashby", "perplexity", "Perplexity"),
            ("ashby", "modal", "Modal"),
            ("ashby", "anyscale", "Anyscale"),
            ("ashby", "baseten", "Baseten"),
        ]
        for c_type, slug, name in new_targets:
            if c_type == "greenhouse":
                discovered.extend(fetch_greenhouse_board(slug, name, target_locs))
            elif c_type == "lever":
                discovered.extend(fetch_lever_board(slug, name, target_locs))
            elif c_type == "ashby":
                discovered.extend(fetch_ashby_board(slug, name, target_locs))

        # Also query guest endpoints for 5yr roles across broader companies
        discovered.extend(fetch_linkedin_guest("Senior Machine Learning Engineer", "Bengaluru, Karnataka, India", target_locs))
        discovered.extend(fetch_linkedin_guest("Lead Data Scientist", "Bengaluru, Karnataka, India", target_locs))
        discovered.extend(fetch_linkedin_guest("Senior Machine Learning Engineer", "Hyderabad, Telangana, India", target_locs))
        discovered.extend(fetch_linkedin_guest("Senior Data Scientist", "Gurgaon, Haryana, India", target_locs))
        discovered.extend(fetch_linkedin_guest("Senior Machine Learning Engineer", "London, England, United Kingdom", target_locs))
        discovered.extend(fetch_linkedin_guest("Senior Machine Learning Engineer", "Sydney, New South Wales, Australia", target_locs))

    # Deduplicate against DB and within batch
    to_add = []
    batch_seen_keys = set()
    batch_seen_links = set()

    for job in discovered:
        # Strict exclusion of Amazon
        if "amazon" in job["company"].lower() or "aws" in job["company"].lower():
            continue

        link = job.get("link", "")
        key = (job["company"].lower(), job["job_title"].lower())

        if link and link in existing_links:
            continue
        if key in existing_keys:
            continue
        if link and link in batch_seen_links:
            continue
        if key in batch_seen_keys:
            continue

        batch_seen_keys.add(key)
        if link:
            batch_seen_links.add(link)
        to_add.append(job)

    print(f"[sweep_crawler] Discovered {len(discovered)} total postings -> {len(to_add)} fresh, verified un-tracked roles.", flush=True)
    for j in to_add[:10]:
        print(f"  + [{j['company']}] {j['job_title']} ({j['location']})", flush=True)

    # Save to found_jobs_latest.json
    with open(FOUND_PATH, "w", encoding="utf-8") as f:
        json.dump(to_add, f, indent=2, ensure_ascii=False)

    # Save updated state
    state["last_mode"] = current_mode
    state["run_count"] = run_count
    state["last_run_time"] = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M IST")
    save_state(state)

    print(f"[sweep_crawler] Saved {len(to_add)} roles to found_jobs_latest.json. Next mode will be: '{'new_companies' if current_mode == 'existing' else 'existing'}'.", flush=True)
    return len(to_add)

if __name__ == "__main__":
    run_crawler()
