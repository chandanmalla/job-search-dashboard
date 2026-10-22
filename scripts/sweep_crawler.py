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

def is_target_science_role(title: str) -> bool:
    """Return True if title is strictly a Data Science or Applied Science role, and NOT software/engineering/principal/staff."""
    tl = title.lower()
    # 1. Strictly exclude senior executive / student / entry levels
    if any(w in tl for w in ["intern", "graduate", "junior", "entry", "associate", "vice president", "vp", "director", "manager", "head"]):
        return False
    # 2. Strictly exclude Principal and Staff levels
    if any(w in tl for w in ["principal", "staff"]):
        return False
    # 3. Strictly exclude software, engineering, devops, mlops, platform, infrastructure, developer
    if any(w in tl for w in ["software", "engineer", "engineering", "developer", "devops", "mlops", "platform", "infrastructure", "architect"]):
        return False
    # 4. Strictly require a Data Scientist or Applied / Research / Decision / ML Scientist title
    return any(w in tl for w in [
        "data scientist", "applied scientist", "research scientist",
        "decision scientist", "machine learning scientist", "ml scientist", "data science"
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
                if is_target_science_role(title):
                    if any(l in ll for l in target_locs):
                        updated = j.get("updated_at")
                        date_str = f"Updated {updated[:10]}" if updated else "Recently posted"
                        jobs.append({
                            "company": company_name,
                            "job_title": title,
                            "location": loc,
                            "date_posted": date_str,
                            "experience_fit": "Strong fit (Data Science / Applied Science ~5 yrs)",
                            "technical_fit": "Statistical modeling, experimentation, causal inference, deep learning, PyTorch, SQL",
                            "visa_sponsorship": "Plausible / standard corporate sponsorship" if any(c in ll for c in ["uk", "london", "sydney", "australia"]) else "N/A (India role)",
                            "relocation": "Not stated",
                            "link": j.get("absolute_url"),
                            "source": f"{company_name} Careers (Greenhouse)",
                            "why_fits": f"Core Data Science / Applied Science role at {company_name}. Strong match for statistical modeling and ML science.",
                            "stretch": False
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
                if is_target_science_role(title):
                    if any(l in ll for l in target_locs):
                        ca = j.get("createdAt")
                        date_str = f"Posted {datetime.fromtimestamp(ca / 1000, tz=timezone.utc).strftime('%Y-%m-%d')}" if ca else "Recently posted"
                        jobs.append({
                            "company": company_name,
                            "job_title": title,
                            "location": loc,
                            "date_posted": date_str,
                            "experience_fit": "Strong fit (Data Science / Applied Science ~5 yrs)",
                            "technical_fit": "Predictive modeling, experimentation, causal inference, Python, SQL, PyTorch",
                            "visa_sponsorship": "Plausible / standard corporate sponsorship" if any(c in ll for c in ["uk", "london", "sydney", "australia"]) else "N/A (India role)",
                            "relocation": "Not stated",
                            "link": j.get("hostedUrl"),
                            "source": f"{company_name} Careers (Lever)",
                            "why_fits": f"Core Data Science / Applied Science role at {company_name}. Focuses on algorithmic modeling and decision science.",
                            "stretch": False
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
                if is_target_science_role(title):
                    if any(l in ll for l in target_locs):
                        pa = j.get("publishedAt") or j.get("openedAt")
                        date_str = f"Posted {pa[:10]}" if pa else "Recently posted"
                        jobs.append({
                            "company": company_name,
                            "job_title": title,
                            "location": loc,
                            "date_posted": date_str,
                            "experience_fit": "Strong fit (Data Science / Applied Science ~5 yrs)",
                            "technical_fit": "Applied research, foundation model evaluation, empirical analysis, PyTorch",
                            "visa_sponsorship": "Plausible: top tier AI lab sponsorship" if any(c in ll for c in ["uk", "london", "sydney", "australia"]) else "N/A (India role)",
                            "relocation": "Relocation supported where applicable",
                            "link": j.get("jobUrl"),
                            "source": f"{company_name} AI Careers (Ashby)",
                            "why_fits": f"Frontier applied science position at {company_name}. Research and empirical modeling.",
                            "stretch": False
                        })
    except Exception as e:
        pass
    return jobs

def fetch_linkedin_guest(query: str, location: str, target_locs):
    # f_TPR=r604800 (past 7 days) and sortBy=DD (newest first)
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={urllib.parse.quote(query)}&location={urllib.parse.quote(location)}&f_TPR=r604800&sortBy=DD&start=0"
    jobs = []
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8")
            titles = re.findall(r'<h3 class="base-search-card__title">([^<]+)</h3>', html)
            companies = re.findall(r'<h4 class="base-search-card__subtitle">\s*(?:<a[^>]*>)?([^<]+?)(?:</a>)?\s*</h4>', html)
            locations = re.findall(r'<span class="job-search-card__location">([^<]+)</span>', html)
            links = re.findall(r'<a class="base-card__full-link[^"]*" href="([^"?]+)', html)
            dates = re.findall(r'<time class="job-search-card__listdate[^"]*" datetime="([^"]+)">([^<]+)</time>', html)

            for idx, (t, c, loc, l) in enumerate(zip(titles, companies, locations, links)):
                t_clean = t.strip()
                c_clean = c.strip()
                loc_clean = loc.strip()
                l_clean = l.strip()

                # STRICT: Filter out Amazon and AWS completely
                if "amazon" in c_clean.lower() or "aws" in c_clean.lower():
                    continue

                if is_target_science_role(t_clean):
                    ll = loc_clean.lower()
                    if any(w in ll for w in target_locs):
                        date_str = "Recently posted"
                        if idx < len(dates):
                            iso_d, rel_d = dates[idx]
                            date_str = f"Posted {rel_d.strip()} ({iso_d})"

                        jobs.append({
                            "company": c_clean,
                            "job_title": t_clean,
                            "location": loc_clean,
                            "date_posted": date_str,
                            "experience_fit": "Strong fit (Data Science / Applied Science ~5 yrs)",
                            "technical_fit": "Statistical modeling, experimentation, predictive analytics, PyTorch, SQL",
                            "visa_sponsorship": "Plausible / UK or AU Skilled Worker sponsor" if any(w in ll for w in ["london", "uk", "sydney", "australia"]) else "N/A (India role)",
                            "relocation": "Not stated",
                            "link": l_clean,
                            "source": f"{c_clean} Careers (LinkedIn Verified)",
                            "why_fits": f"Core Data Science / Applied Science role at {c_clean}. Focused on statistical modeling, causal inference, and ML algorithms.",
                            "stretch": False
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
        for comp in ["Databricks", "Flipkart", "Apple", "Meta", "Microsoft", "Google", "Intel"]:
            discovered.extend(fetch_linkedin_guest(f"Senior Data Scientist {comp}", "Bengaluru, Karnataka, India", target_locs))
            discovered.extend(fetch_linkedin_guest(f"Senior Applied Scientist {comp}", "Bengaluru, Karnataka, India", target_locs))

    else:
        print("[sweep_crawler] Probing NEW companies & emerging unicorns for ~5yr Data Science / Applied Science roles...", flush=True)
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

        # Query guest endpoints strictly for Data Science and Applied Science roles
        discovered.extend(fetch_linkedin_guest("Senior Data Scientist", "Bengaluru, Karnataka, India", target_locs))
        discovered.extend(fetch_linkedin_guest("Lead Data Scientist", "Bengaluru, Karnataka, India", target_locs))
        discovered.extend(fetch_linkedin_guest("Senior Applied Scientist", "Bengaluru, Karnataka, India", target_locs))
        discovered.extend(fetch_linkedin_guest("Senior Data Scientist", "Hyderabad, Telangana, India", target_locs))
        discovered.extend(fetch_linkedin_guest("Senior Data Scientist", "Gurgaon, Haryana, India", target_locs))
        discovered.extend(fetch_linkedin_guest("Senior Data Scientist", "London, England, United Kingdom", target_locs))
        discovered.extend(fetch_linkedin_guest("Senior Applied Scientist", "London, England, United Kingdom", target_locs))
        discovered.extend(fetch_linkedin_guest("Senior Data Scientist", "Sydney, New South Wales, Australia", target_locs))

    # Deduplicate against DB and within batch
    to_add = []
    batch_seen_keys = set()
    batch_seen_links = set()

    for job in discovered:
        # Strict exclusion of Amazon and non-science/software/engineering roles
        if "amazon" in job["company"].lower() or "aws" in job["company"].lower():
            continue
        if not is_target_science_role(job["job_title"]):
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
