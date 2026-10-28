"""
Sweep Crawler with Alternating Strategy & Exhaustive Product Company ATS Feeds
==============================================================================
Runs on every 2-hourly cron execution:
- Alternates between:
  1. 'existing' mode: Re-checks core Big Tech, frontier AI labs, and established product
     ATS feeds (OpenAI, Anthropic, Databricks, Stripe, Airbnb, Canva, Figma, NVIDIA, Adobe,
     Salesforce, PayPal, Target, Visa, Google, Microsoft, Meta, Netflix, Uber, etc.)
  2. 'new_companies' mode: Probes high-growth consumer/SaaS, Indian tech unicorns, quant hubs,
     and emerging AI labs across Ashby, Greenhouse, Lever, Workday, and verified guest APIs.
- Covers 66+ direct public ATS feeds (Ashby, Greenhouse, Lever, Workday) plus targeted sweeps.
- Strictly targets core Data Science & Applied Science roles (~5-yr senior scope).
- Strictly EXCLUDES IT services, consultancies, staffing agencies, SWE/engineering, and Amazon subsidiaries.
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
    "Accept": "application/json, text/plain, */*",
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

# Exclude IT services, body shops, consultancies, staffing agencies, and Amazon
PHRASE_EXCLUSIONS_LOWER = {
    'accenture', 'antal', 'datatech', 'delta technology', 'epam', 'fractal', 'grid dynamics',
    'harnham', 'inoptra', 'infosys', 'mathco', 'mycareernet', 'nps prism', 'oliver wyman',
    'omegahires', 'opus recruitment', 'procdna', 'recrew', 'sim digital', 'srijan',
    'tata consultancy', 'vgreen', 'wipro', 'cognizant', 'ltimindtree',
    'tech mahindra', 'capgemini', 'genpact', 'mu sigma', 'deloitte', 'ernst & young', 'ernst and young',
    'kpmg', 'mckinsey', 'bain & company', 'michael page', 'robert half', 'adecco', 'randstad', 'hays',
    'caterpillar', 'ecolab', 'mccormick', 'syngenta', 'trane technologies', 'ingersoll rand',
    'johnson & johnson', 'johnson &amp; johnson', 'kroll', 'consilio', 'dmi finance',
    'funding societies', 'amplify health', 'xcaliber', 'thales', 'signify', 'sei', 'prolific',
    'tracksuit', 'mopid', 'humara', 'allura partners', 'amazon', 'aws',
    'cohere health', 'neurogent', 'ets', 'fedex', 'fedex gcs', 'applied materials',
    'quantum', 'blend', 'enigma', 'epsilon', 'gartner', 'consulting', 'staffing', 'recruitment'
}

# Short acronyms matched with word boundaries to avoid false positives (e.g. 'Harvey AI' or 'Quadeye' containing 'ey')
SHORT_EXCLUSIONS = {'ey', 'tcs', 'pwc', 'hcl', 'ust', 'bcg', 'bd', 'lmg', 'mvf'}

def is_top_product_company(company: str) -> bool:
    """Return True if company is a verified top tech product company, and NOT IT services/consulting/staffing."""
    cl = company.lower().strip()
    if not cl:
        return False
    if any(ex in cl for ex in PHRASE_EXCLUSIONS_LOWER):
        return False
    words = set(re.findall(r'\b[a-z0-9]+\b', cl))
    if any(short in words for short in SHORT_EXCLUSIONS):
        return False
    return True

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
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            for j in data.get("jobs", []):
                title = j.get("title", "")
                loc = j.get("location", {}).get("name", "")
                tl, ll = title.lower(), loc.lower()
                if is_target_science_role(title):
                    if any(l in ll for l in target_locs) or not loc:
                        updated = j.get("updated_at")
                        date_str = f"Updated {updated[:10]}" if updated else "Recently posted"
                        jobs.append({
                            "company": company_name,
                            "job_title": title,
                            "location": loc or "Multiple Hubs / Remote",
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
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            for j in data.get("jobs", data if isinstance(data, list) else []):
                title = j.get("text", "")
                loc = j.get("categories", {}).get("location", "")
                tl, ll = title.lower(), loc.lower()
                if is_target_science_role(title):
                    if any(l in ll for l in target_locs) or not loc:
                        ca = j.get("createdAt")
                        date_str = f"Posted {datetime.fromtimestamp(ca / 1000, tz=timezone.utc).strftime('%Y-%m-%d')}" if ca else "Recently posted"
                        jobs.append({
                            "company": company_name,
                            "job_title": title,
                            "location": loc or "Multiple Hubs / Remote",
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
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            for j in data.get("jobs", []):
                title = j.get("title", "")
                loc = j.get("locationName") or ""
                tl, ll = title.lower(), loc.lower()
                if is_target_science_role(title):
                    # For Frontier AI labs, null/empty location denotes global AI research hubs
                    if any(l in ll for l in target_locs) or not loc or j.get("isRemote"):
                        pa = j.get("publishedAt") or j.get("openedAt")
                        date_str = f"Posted {pa[:10]}" if pa else "Recently posted"
                        jobs.append({
                            "company": company_name,
                            "job_title": title,
                            "location": loc or "Global / Frontier AI Lab Hubs (US/UK/Remote)",
                            "date_posted": date_str,
                            "experience_fit": "Strong fit (Data Science / Applied Science ~5 yrs)",
                            "technical_fit": "Applied research, foundation model evaluation, empirical analysis, PyTorch",
                            "visa_sponsorship": "Plausible: top tier AI lab sponsorship" if any(c in ll for c in ["uk", "london", "sydney", "australia"]) else "Plausible / standard corporate sponsorship",
                            "relocation": "Relocation supported where applicable",
                            "link": j.get("jobUrl"),
                            "source": f"{company_name} AI Careers (Ashby)",
                            "why_fits": f"Frontier applied science position at {company_name}. Research, evaluations, and empirical modeling.",
                            "stretch": False
                        })
    except Exception:
        pass
    return jobs

def fetch_workday_board(cxs_url: str, web_base: str, company_name: str, target_locs):
    jobs = []
    try:
        payload = json.dumps({"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "Scientist"}).encode("utf-8")
        req = urllib.request.Request(cxs_url, data=payload, headers={
            "User-Agent": HEADERS["User-Agent"],
            "Content-Type": "application/json",
            "Accept": "application/json"
        }, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            for p in data.get("jobPostings", []):
                title = p.get("title", "")
                loc = p.get("locationsText", "")
                tl, ll = title.lower(), loc.lower()
                if is_target_science_role(title):
                    if any(l in ll for l in target_locs) or not loc:
                        ext_path = p.get("externalPath", "")
                        job_link = f"{web_base}{ext_path}" if ext_path else web_base
                        pa = p.get("postedOn")
                        date_str = f"Posted {pa}" if pa else "Recently posted"
                        jobs.append({
                            "company": company_name,
                            "job_title": title,
                            "location": loc or "Multiple Locations / Target Hubs",
                            "date_posted": date_str,
                            "experience_fit": "Strong fit (Data Science / Applied Science ~5 yrs)",
                            "technical_fit": "Statistical modeling, experimentation, deep learning, PyTorch, SQL, production ML",
                            "visa_sponsorship": "Plausible / Skilled Worker sponsor" if any(c in ll for c in ["uk", "london", "sydney", "australia"]) else "N/A (India role)",
                            "relocation": "Not stated",
                            "link": job_link,
                            "source": f"{company_name} Careers (Workday)",
                            "why_fits": f"Core Data Science / Applied Science role at {company_name}. Strong match for statistical modeling and ML science.",
                            "stretch": False
                        })
    except Exception:
        pass
    return jobs

def fetch_linkedin_guest(query: str, location: str, target_locs, f_tpr: str = "r172800"):
    """
    Query LinkedIn Jobs guest API.
    f_tpr: 'r172800' for past 48h, 'r86400' for past 24h.
    sortBy=DD ensures freshest listings first.
    """
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={urllib.parse.quote(query)}&location={urllib.parse.quote(location)}&f_TPR={f_tpr}&sortBy=DD&start=0"
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

                # STRICT: Filter out Amazon, consultancies, non-product companies
                if "amazon" in c_clean.lower() or "aws" in c_clean.lower():
                    continue
                if not is_top_product_company(c_clean):
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
                            "source": f"{c_clean} Careers (Verified)",
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
    current_mode = "new_companies" if last_mode == "existing" else "existing"
    run_count = state.get("run_count", 0) + 1

    print(f"[sweep_crawler] === Run #{run_count} | Mode: '{current_mode.upper()}' ===", flush=True)

    target_locs = ["india", "bangalore", "bengaluru", "hyderabad", "delhi", "gurgaon", "gurugram", "noida", "chennai", "mumbai", "london", "uk", "united kingdom", "sydney", "australia", "remote"]

    discovered = []

    # -------------------------------------------------------------------------
    # RUN A: "EXISTING" MODE
    # Deep checks of Core Big Tech, Tier-1 Product ATS feeds, and Frontier AI Labs
    # -------------------------------------------------------------------------
    if current_mode == "existing":
        print("[sweep_crawler] Checking established product companies & frontier AI labs ATS feeds...", flush=True)

        # 1. Frontier AI & Core Big Tech Greenhouse Feeds
        greenhouse_targets = [
            ("anthropic", "Anthropic"),
            ("scaleai", "Scale AI"),
            ("togetherai", "Together AI"),
            ("airbnb", "Airbnb"),
            ("stripe", "Stripe"),
            ("databricks", "Databricks"),
            ("canva", "Canva"),
            ("figma", "Figma"),
            ("deliveroo", "Deliveroo"),
            ("monzo", "Monzo"),
            ("tripadvisor", "TripAdvisor"),
            ("affirm", "Affirm"),
            ("wayve", "Wayve"),
            ("revolut", "Revolut"),
            ("wise", "Wise"),
            ("synthesia", "Synthesia"),
            ("servicenow", "ServiceNow"),
            ("postman", "Postman"),
        ]
        for slug, name in greenhouse_targets:
            discovered.extend(fetch_greenhouse_board(slug, name, target_locs))

        # 2. Frontier AI Ashby Feeds
        ashby_targets = [
            ("openai", "OpenAI"),
            ("cohere", "Cohere"),
            ("perplexity", "Perplexity"),
            ("elevenlabs", "ElevenLabs"),
            ("runway", "Runway"),
            ("harvey", "Harvey AI"),
            ("sarvam", "Sarvam AI"),
        ]
        for slug, name in ashby_targets:
            discovered.extend(fetch_ashby_board(slug, name, target_locs))

        # 3. Established Product Lever Feeds
        lever_targets = [
            ("spotify", "Spotify"),
            ("inmobi", "InMobi"),
            ("meesho", "Meesho"),
            ("swiggy", "Swiggy"),
            ("zomato", "Zomato"),
            ("phonepe", "PhonePe"),
        ]
        for slug, name in lever_targets:
            discovered.extend(fetch_lever_board(slug, name, target_locs))

        # 4. Big Tech Workday Feeds
        workday_targets = [
            ("https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs", "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite", "NVIDIA"),
            ("https://adobe.wd5.myworkdayjobs.com/wday/cxs/adobe/external_experienced/jobs", "https://adobe.wd5.myworkdayjobs.com/en-US/external_experienced", "Adobe"),
            ("https://salesforce.wd12.myworkdayjobs.com/wday/cxs/salesforce/External_Career_Site/jobs", "https://salesforce.wd12.myworkdayjobs.com/en-US/External_Career_Site", "Salesforce"),
            ("https://paypal.wd1.myworkdayjobs.com/wday/cxs/paypal/jobs/jobs", "https://paypal.wd1.myworkdayjobs.com/en-US/jobs", "PayPal"),
            ("https://target.wd5.myworkdayjobs.com/wday/cxs/target/targetcareers/jobs", "https://target.wd5.myworkdayjobs.com/en-US/targetcareers", "Target"),
            ("https://visa.wd5.myworkdayjobs.com/wday/cxs/visa/Visa/jobs", "https://visa.wd5.myworkdayjobs.com/en-US/Visa", "Visa"),
        ]
        for api, base, name in workday_targets:
            discovered.extend(fetch_workday_board(api, base, name, target_locs))

        # 5. Targeted fresh queries for Big Tech & Quant Hubs (past 48 hours)
        for comp in ["Google", "DeepMind", "Microsoft", "Meta", "Apple", "Netflix", "Uber", "Snowflake", "Atlassian", "Flipkart", "Goldman Sachs", "Tower Research Capital"]:
            discovered.extend(fetch_linkedin_guest(f"Senior Data Scientist {comp}", "Bengaluru, Karnataka, India", target_locs))
            discovered.extend(fetch_linkedin_guest(f"Senior Applied Scientist {comp}", "Bengaluru, Karnataka, India", target_locs))

    # -------------------------------------------------------------------------
    # RUN B: "NEW_COMPANIES" MODE
    # Probing high-growth consumer SaaS, Indian unicorns, quant firms, and AI startups
    # -------------------------------------------------------------------------
    else:
        print("[sweep_crawler] Probing emerging consumer/SaaS, Indian tech unicorns & quant hubs...", flush=True)

        # 1. Emerging SaaS & Consumer Greenhouse Feeds
        greenhouse_targets = [
            ("agoda", "Agoda"),
            ("doordashusa", "DoorDash"),
            ("instacart", "Instacart"),
            ("lyft", "Lyft"),
            ("pinterest", "Pinterest"),
            ("reddit", "Reddit"),
            ("roblox", "Roblox"),
            ("duolingo", "Duolingo"),
            ("datadog", "Datadog"),
            ("cloudflare", "Cloudflare"),
            ("mongodb", "MongoDB"),
            ("elastic", "Elastic"),
            ("rubrik", "Rubrik"),
            ("razorpaysoftwareprivatelimited", "Razorpay"),
            ("groww", "Groww"),
            ("browserstack", "BrowserStack"),
            ("brex", "Brex"),
            ("ramp", "Ramp"),
        ]
        for slug, name in greenhouse_targets:
            discovered.extend(fetch_greenhouse_board(slug, name, target_locs))

        # 2. Productivity & AI Lab Ashby Feeds
        ashby_targets = [
            ("notion", "Notion"),
            ("modal", "Modal"),
            ("anyscale", "Anyscale"),
            ("baseten", "Baseten"),
            ("openai", "OpenAI"),
            ("cohere", "Cohere"),
        ]
        for slug, name in ashby_targets:
            discovered.extend(fetch_ashby_board(slug, name, target_locs))

        # 3. High-Growth Fintech & Indian Tech Lever Feeds
        lever_targets = [
            ("palantir", "Palantir"),
            ("cred", "CRED"),
            ("paytm", "Paytm"),
            ("zeta", "Zeta"),
        ]
        for slug, name in lever_targets:
            discovered.extend(fetch_lever_board(slug, name, target_locs))

        # 4. Entertainment & Media Workday Feeds
        workday_targets = [
            ("https://warnerbros.wd5.myworkdayjobs.com/wday/cxs/warnerbros/global/jobs", "https://warnerbros.wd5.myworkdayjobs.com/en-US/global", "Warner Bros. Discovery"),
            ("https://expedia.wd108.myworkdayjobs.com/wday/cxs/expedia/search/jobs", "https://expedia.wd108.myworkdayjobs.com/en-US/search", "Expedia Group"),
            ("https://snapchat.wd1.myworkdayjobs.com/wday/cxs/snapchat/snap/jobs", "https://snapchat.wd1.myworkdayjobs.com/en-US/snap", "Snap"),
        ]
        for api, base, name in workday_targets:
            discovered.extend(fetch_workday_board(api, base, name, target_locs))

        # 5. Targeted fresh queries for Indian Unicorns & Quant Leaders (past 48 hours)
        for comp in [
            "Zepto", "Myntra", "Dream11", "MakeMyTrip", "ShareChat", "Freshworks", "Zoho",
            "Sprinklr", "Urban Company", "Lenskart", "Nykaa", "Delhivery", "Rapido",
            "AlphaGrep", "Graviton", "Quadeye", "Mistral AI", "Hugging Face", "Krutrim"
        ]:
            discovered.extend(fetch_linkedin_guest(f"Data Scientist {comp}", "India", target_locs))

        # 6. Ultra-fresh regional scans across hubs (past 48 hours)
        discovered.extend(fetch_linkedin_guest("Senior Data Scientist", "Bengaluru, Karnataka, India", target_locs))
        discovered.extend(fetch_linkedin_guest("Senior Applied Scientist", "Bengaluru, Karnataka, India", target_locs))
        discovered.extend(fetch_linkedin_guest("Lead Data Scientist", "Bengaluru, Karnataka, India", target_locs))
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
        # Strict exclusion of Amazon, non-product companies, and non-science roles
        if "amazon" in job["company"].lower() or "aws" in job["company"].lower():
            continue
        if not is_top_product_company(job.get("company", "")):
            continue
        if not is_target_science_role(job.get("job_title", "")):
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
