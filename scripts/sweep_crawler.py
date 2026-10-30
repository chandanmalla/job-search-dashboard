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

import sys as _sys
_sys.path.insert(0, r"C:\Users\chand\Downloads\Job Search\job-tracker")
import job_filters as JF

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
    'funding societies', 'amplify health', 'xcaliber', 'thales', 'signify', 'prolific',
    'tracksuit', 'mopid', 'humara', 'allura partners', 'amazon', 'aws',
    'cohere health', 'neurogent', 'fedex', 'twitch', 'audible', 'zoox', 'whole foods', 'imdb', 'zappos', 'annapurna labs', 'pricewaterhouse', 'tata consultancy services', 'bain and company', 'boston consulting', 'fedex gcs', 'applied materials',
    'quantum', 'blend', 'enigma', 'epsilon', 'gartner', 'consulting', 'staffing', 'recruitment'
}

# Short acronyms matched with word boundaries to avoid false positives (e.g. 'Harvey AI' or 'Quadeye' containing 'ey')
SHORT_EXCLUSIONS = {'ey', 'tcs', 'pwc', 'hcl', 'ust', 'bcg', 'bd', 'lmg', 'mvf', 'ets', 'sei', 'bain', 'aws', 'ltts', 'lti', 'mphasis'}

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
    """Strict include/exclude for core Data Science / Applied Science roles (~5 yrs)."""
    tl = title.lower()
    EXCL = [r"\bintern", r"\bgraduate", r"\bjunior", r"\bentry", r"\bassociate", r"\bvice president", r"\bvp\b",
            r"\bdirector", r"\bmanager", r"\bhead\b", r"\bprincipal", r"\bstaff\b", r"\bsoftware", r"\bswe\b",
            r"engineer", r"\bdeveloper", r"devops", r"mlops", r"\bplatform", r"infrastructure", r"architect",
            r"full[- ]?stack", r"front[- ]?end", r"back[- ]?end", r"data engineer", r"\bfellow", r"\bphd\b"]
    if any(re.search(p, tl) for p in EXCL):
        return False
    return any(w in tl for w in [
        "data scientist", "applied scientist", "research scientist",
        "decision scientist", "machine learning scientist", "ml scientist", "data science"
    ])

# Per-source crawl stats (printed + saved each run so silent failures are visible)
STATS = []
LAST_ERR = []

def tracked(kind, name, fn, *args):
    LAST_ERR.clear()
    res = fn(*args)
    STATS.append({"type": kind, "source": name, "kept": len(res), "error": LAST_ERR[0] if LAST_ERR else ""})
    return res

def reloc_tracked(kind, name, fn, *args):
    """Like tracked(), but accepts relocation hubs and tags the relocation field from the posting text."""
    RELOC_ON[0] = True
    try:
        res = tracked(kind, "[reloc] " + name, fn, *args)
    finally:
        RELOC_ON[0] = False
    for j in res:
        txt = (j.get("job_title", "") + " " + j.get("_desc", "")).lower()
        if "relocat" in txt:
            j["relocation"] = "Relocation mentioned in posting"
        elif not any(h in j.get("location", "").lower() for h in _LOC_HUBS):
            j["relocation"] = "Relocation-friendly employer (not stated in posting)"
        if not any(h in j.get("location", "").lower() for h in _LOC_HUBS):
            j["visa_sponsorship"] = "Employer-sponsored work visa typical (check posting)"
    return res



_LOC_HUBS = ["india", "bangalore", "bengaluru", "hyderabad", "delhi", "gurgaon", "gurugram", "noida", "chennai",
             "mumbai", "pune", "london", "england", "united kingdom", "great britain", "sydney", "melbourne", "australia"]
# Relocation hubs: only accepted for RELOC sources (companies that relocate hires from India)
_RELOC_HUBS = ["bangkok", "thailand", "singapore", "kuala lumpur", "petaling jaya", "malaysia", "jakarta",
               "indonesia", "amsterdam", "netherlands", "berlin", "germany", "dusseldorf", "d\u00fcsseldorf",
               "dublin", "ireland", "tokyo", "japan", "dubai", "united arab emirates"]
RELOC_ON = [False]
def loc_ok(ll: str) -> bool:
    """India / UK / Australia hubs, or a plain (non-US/EU-restricted) Remote.
    For relocation sources, also Bangkok/Singapore/KL/Jakarta/Amsterdam/Berlin/Dublin/Tokyo/Dubai."""
    ll = (ll or "").lower()
    if RELOC_ON[0] and (any(h in ll for h in _RELOC_HUBS) or re.search(r"\b(sg|th|my|id|nl|de|ie|jp|ae)\b", ll)):
        return True
    if any(h in ll for h in _LOC_HUBS) or re.search(r"\b(uk|gb|nsw|vic)\b", ll):
        return True
    if "remote" in ll:
        rest = re.sub(r"remote|global|worldwide|anywhere|apac|emea|[^a-z]", "", ll)
        return rest == ""
    return False

def fetch_greenhouse_board(slug: str, company_name: str, target_locs):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    jobs = []
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
            for j in data.get("jobs", []):
                title = j.get("title", "")
                loc = j.get("location", {}).get("name", "")
                tl, ll = title.lower(), loc.lower()
                if is_target_science_role(title):
                    if loc_ok(ll) or not loc:
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
                            "_desc": __import__("html").unescape(j.get("content") or ""),
                            "why_fits": f"Core Data Science / Applied Science role at {company_name}. Strong match for statistical modeling and ML science.",
                            "stretch": False
                        })
    except Exception as e:
        LAST_ERR.append(f"{type(e).__name__}: {str(e)[:100]}")
    return jobs

def fetch_lever_board(slug: str, company_name: str, target_locs):
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    jobs = []
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
            for j in (data if isinstance(data, list) else data.get("jobs", [])):
                title = j.get("text", "")
                loc = j.get("categories", {}).get("location", "")
                tl, ll = title.lower(), loc.lower()
                if is_target_science_role(title):
                    if loc_ok(ll) or not loc:
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
                            "_desc": (j.get("descriptionPlain") or "") + " " + " ".join((l.get("content") or "") for l in (j.get("lists") or [])) + " " + (j.get("additionalPlain") or ""),
                            "why_fits": f"Core Data Science / Applied Science role at {company_name}. Focuses on algorithmic modeling and decision science.",
                            "stretch": False
                        })
    except Exception as e:
        LAST_ERR.append(f"{type(e).__name__}: {str(e)[:100]}")
    return jobs

def fetch_ashby_board(slug: str, company_name: str, target_locs):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    jobs = []
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
            for j in data.get("jobs", []):
                title = j.get("title", "")
                loc = j.get("locationName") or (j.get("location") if RELOC_ON[0] else "") or ""
                tl, ll = title.lower(), loc.lower()
                if is_target_science_role(title):
                    # For Frontier AI labs, null/empty location denotes global AI research hubs
                    if loc_ok(ll) or not loc:
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
                            "_desc": j.get("descriptionPlain") or j.get("descriptionHtml") or "",
                            "why_fits": f"Frontier applied science position at {company_name}. Research, evaluations, and empirical modeling.",
                            "stretch": False
                        })
    except Exception as e:
        LAST_ERR.append(f"{type(e).__name__}: {str(e)[:100]}")
    return jobs

def fetch_workday_board(cxs_url: str, web_base: str, company_name: str, target_locs):
    jobs = []
    try:
        postings = []
        for off in range(0, 200, 20):
            payload = json.dumps({"appliedFacets": {}, "limit": 20, "offset": off, "searchText": "Scientist"}).encode("utf-8")
            req = urllib.request.Request(cxs_url, data=payload, headers={
                "User-Agent": HEADERS["User-Agent"],
                "Content-Type": "application/json",
                "Accept": "application/json"
            }, method="POST")
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
            page = data.get("jobPostings", [])
            postings.extend(page)
            if len(page) < 20 or off + 20 >= (data.get("total") or 0):
                break
        if True:
            for p in postings:
                title = p.get("title", "")
                loc = p.get("locationsText", "")
                tl, ll = title.lower(), loc.lower()
                if is_target_science_role(title):
                    if loc_ok(ll) or not loc:
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
    except Exception as e:
        LAST_ERR.append(f"{type(e).__name__}: {str(e)[:100]}")
    return jobs

def fetch_smartrecruiters_board(slug: str, company_name: str, target_locs):
    jobs = []
    try:
        for off in range(0, 1000, 100):
            url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={off}"
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
            content = data.get("content", [])
            for j in content:
                title = j.get("name", "")
                L = j.get("location", {}) or {}
                loc = ", ".join(x for x in [L.get("city"), L.get("country", "").upper()] if x)
                if L.get("remote"):
                    loc += " (Remote)"
                ll = loc.lower().replace(", in", ", india").replace(", gb", ", uk").replace(", au", ", australia")
                if is_target_science_role(title) and (loc_ok(ll) or not loc):
                    rd = j.get("releasedDate")
                    jobs.append({
                        "company": company_name, "job_title": title, "location": loc or "Multiple Hubs",
                        "date_posted": f"Posted {rd[:10]}" if rd else "Recently posted",
                        "experience_fit": "Strong fit (Data Science / Applied Science ~5 yrs)",
                        "technical_fit": "Statistical modeling, experimentation, ML, Python, SQL",
                        "visa_sponsorship": "Plausible / standard corporate sponsorship" if any(c in ll for c in ["uk", "london", "sydney", "melbourne", "australia"]) else "N/A (India role)",
                        "relocation": "Not stated",
                        "link": f"https://jobs.smartrecruiters.com/{slug}/{j.get('id')}",
                        "source": f"{company_name} Careers (SmartRecruiters)",
                        "why_fits": f"Core Data Science / Applied Science role at {company_name}.",
                        "stretch": False
                    })
            if off + 100 >= data.get("totalFound", 0):
                break
    except Exception as e:
        LAST_ERR.append(f"{type(e).__name__}: {str(e)[:100]}")
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
        with urllib.request.urlopen(req, timeout=20) as resp:
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
                    if loc_ok(ll):
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

    except Exception as e:
        LAST_ERR.append(f"{type(e).__name__}: {str(e)[:100]}")
    return jobs


def run_crawler(force_mode=None, dry_run=False):
    state = load_state()
    db = load_db()

    existing_links = {j.get("link") for j in db["all_jobs"] if j.get("link")}
    existing_keys = {(j.get("company", "").lower(), j.get("job_title", "").lower()) for j in db["all_jobs"]}

    last_mode = state.get("last_mode", "new_companies")
    current_mode = force_mode or ("new_companies" if last_mode == "existing" else "existing")
    run_count = state.get("run_count", 0) + 1

    print(f"[sweep_crawler] === Run #{run_count} | Mode: '{current_mode.upper()}' ===", flush=True)

    target_locs = ["india", "bangalore", "bengaluru", "hyderabad", "delhi", "gurgaon", "gurugram", "noida", "chennai", "mumbai", "pune", "london", "england", "melbourne", "uk", "united kingdom", "sydney", "australia", "remote"]

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
            ("figma", "Figma"),
            ("inmobi", "InMobi"),  # moved from Lever (404) to Greenhouse
            ("deliveroo", "Deliveroo"),
            ("monzo", "Monzo"),
            ("tripadvisor", "TripAdvisor"),
            ("affirm", "Affirm"),
            ("wise", "Wise"),
        ]
        for slug, name in greenhouse_targets:
            discovered.extend(tracked("greenhouse", name, fetch_greenhouse_board, slug, name, target_locs))

        # 2. Frontier AI Ashby Feeds
        ashby_targets = [
            ("openai", "OpenAI"),
            ("cohere", "Cohere"),
            ("perplexity", "Perplexity"),
            ("elevenlabs", "ElevenLabs"),
            ("runway", "Runway"),
            ("harvey", "Harvey AI"),
            ("sarvam", "Sarvam AI"),
            ("wayve", "Wayve"),  # moved from Greenhouse (404) to Ashby
            ("synthesia", "Synthesia"),  # moved from Greenhouse (404) to Ashby
        ]
        for slug, name in ashby_targets:
            discovered.extend(tracked("ashby", name, fetch_ashby_board, slug, name, target_locs))

        # 3. Established Product Lever Feeds
        lever_targets = [
            ("spotify", "Spotify"),
            ("meesho", "Meesho"),
            ("eternal", "Zomato (Eternal)"),  # Zomato parent Eternal Ltd on Lever
        ]
        for slug, name in lever_targets:
            discovered.extend(tracked("lever", name, fetch_lever_board, slug, name, target_locs))

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
            discovered.extend(tracked("workday", name, fetch_workday_board, api, base, name, target_locs))

        # 4b. SmartRecruiters public API (boards moved off Greenhouse/Lever)
        for slug, name in [("Canva", "Canva"), ("ServiceNow", "ServiceNow"), ("Swiggy", "Swiggy")]:
            discovered.extend(tracked("smartrecruiters", name, fetch_smartrecruiters_board, slug, name, target_locs))

        # 5. Targeted fresh queries for Big Tech & Quant Hubs (past 48 hours)
        for comp in ["Google", "DeepMind", "Microsoft", "Meta", "Apple", "Netflix", "Uber", "Snowflake", "Atlassian", "Flipkart", "Goldman Sachs", "Tower Research Capital",
                     "Revolut", "Postman", "PhonePe"]:  # last 3: no public ATS API
            discovered.extend(tracked("search48h", f"Senior Data Scientist {comp}", fetch_linkedin_guest, f"Senior Data Scientist {comp}", "Bengaluru, Karnataka, India", target_locs))
            discovered.extend(tracked("search48h", f"Senior Applied Scientist {comp}", fetch_linkedin_guest, f"Senior Applied Scientist {comp}", "Bengaluru, Karnataka, India", target_locs))

    # -------------------------------------------------------------------------
    # RUN B: "NEW_COMPANIES" MODE
    # Probing high-growth consumer SaaS, Indian unicorns, quant firms, and AI startups
    # -------------------------------------------------------------------------
    else:
        print("[sweep_crawler] Probing emerging consumer/SaaS, Indian tech unicorns & quant hubs...", flush=True)

        # 1. Emerging SaaS & Consumer Greenhouse Feeds
        greenhouse_targets = [
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
            ("brex", "Brex"),
            ("ramp", "Ramp"),
        ]
        for slug, name in greenhouse_targets:
            discovered.extend(tracked("greenhouse", name, fetch_greenhouse_board, slug, name, target_locs))

        # 2. Productivity & AI Lab Ashby Feeds
        ashby_targets = [
            ("notion", "Notion"),
            ("modal", "Modal"),
            ("anyscale", "Anyscale"),
            ("baseten", "Baseten"),
        ]
        for slug, name in ashby_targets:
            discovered.extend(tracked("ashby", name, fetch_ashby_board, slug, name, target_locs))

        # 3. High-Growth Fintech & Indian Tech Lever Feeds
        lever_targets = [
            ("palantir", "Palantir"),
            ("cred", "CRED"),
            ("paytm", "Paytm"),
            ("zeta", "Zeta"),
        ]
        for slug, name in lever_targets:
            discovered.extend(tracked("lever", name, fetch_lever_board, slug, name, target_locs))

        # 4. Entertainment & Media Workday Feeds
        workday_targets = [
            ("https://warnerbros.wd5.myworkdayjobs.com/wday/cxs/warnerbros/global/jobs", "https://warnerbros.wd5.myworkdayjobs.com/en-US/global", "Warner Bros. Discovery"),
            ("https://expedia.wd108.myworkdayjobs.com/wday/cxs/expedia/search/jobs", "https://expedia.wd108.myworkdayjobs.com/en-US/search", "Expedia Group"),
            ("https://snapchat.wd1.myworkdayjobs.com/wday/cxs/snapchat/snap/jobs", "https://snapchat.wd1.myworkdayjobs.com/en-US/snap", "Snap"),
        ]
        for api, base, name in workday_targets:
            discovered.extend(tracked("workday", name, fetch_workday_board, api, base, name, target_locs))

        # 5. Targeted fresh queries for Indian Unicorns & Quant Leaders (past 48 hours)
        for comp in [
            "Zepto", "Myntra", "Dream11", "MakeMyTrip", "ShareChat", "Freshworks", "Zoho",
            "Sprinklr", "Urban Company", "Lenskart", "Nykaa", "Delhivery", "Rapido",
            "AlphaGrep", "Graviton", "Quadeye", "Mistral AI", "Hugging Face", "Krutrim",
            "BrowserStack"  # no public ATS API
        ]:
            discovered.extend(tracked("search48h", f"Data Scientist {comp}", fetch_linkedin_guest, f"Data Scientist {comp}", "India", target_locs))

        # 6. Ultra-fresh regional scans across hubs (past 48 hours)
        discovered.extend(tracked("search48h", "Senior Data Scientist", fetch_linkedin_guest, "Senior Data Scientist", "Bengaluru, Karnataka, India", target_locs))
        discovered.extend(tracked("search48h", "Senior Applied Scientist", fetch_linkedin_guest, "Senior Applied Scientist", "Bengaluru, Karnataka, India", target_locs))
        discovered.extend(tracked("search48h", "Lead Data Scientist", fetch_linkedin_guest, "Lead Data Scientist", "Bengaluru, Karnataka, India", target_locs))
        discovered.extend(tracked("search48h", "Senior Data Scientist", fetch_linkedin_guest, "Senior Data Scientist", "Hyderabad, Telangana, India", target_locs))
        discovered.extend(tracked("search48h", "Senior Data Scientist", fetch_linkedin_guest, "Senior Data Scientist", "Gurgaon, Haryana, India", target_locs))
        discovered.extend(tracked("search48h", "Senior Data Scientist", fetch_linkedin_guest, "Senior Data Scientist", "London, England, United Kingdom", target_locs))
        discovered.extend(tracked("search48h", "Senior Applied Scientist", fetch_linkedin_guest, "Senior Applied Scientist", "London, England, United Kingdom", target_locs))
        discovered.extend(tracked("search48h", "Senior Data Scientist", fetch_linkedin_guest, "Senior Data Scientist", "Sydney, New South Wales, Australia", target_locs))

    # -------------------------------------------------------------------------
    # RELOCATION SOURCES (every run): international employers that relocate DS hires from India.
    # Location filter widened to SE Asia / EU / Japan / UAE hubs for these sources only.
    # -------------------------------------------------------------------------
    print("[sweep_crawler] Checking relocation-friendly international employers...", flush=True)
    for slug, name in [("agoda", "Agoda"), ("getyourguide", "GetYourGuide"), ("hellofresh", "HelloFresh"),
                       ("adyen", "Adyen"), ("trivago", "trivago"), ("sumup", "SumUp")]:
        discovered.extend(reloc_tracked("greenhouse", name, fetch_greenhouse_board, slug, name, target_locs))
    discovered.extend(reloc_tracked("ashby", "Airwallex", fetch_ashby_board, "airwallex", "Airwallex", target_locs))
    for slug, name in [("Grab", "Grab"), ("DeliveryHero", "Delivery Hero")]:
        res = reloc_tracked("smartrecruiters", name, fetch_smartrecruiters_board, slug, name, target_locs)
        if slug == "Grab":  # Chandan: Grab only Bangkok (Thailand) and India roles
            india = ["india", "bangalore", "bengaluru", "hyderabad", "delhi", "gurgaon", "gurugram", "noida", "chennai", "mumbai", "pune", ", in"]
            res = [j for j in res if any(h in j.get("location", "").lower() for h in ["bangkok", "thailand", ", th"] + india)]
            STATS[-1]["kept"] = len(res)
        discovered.extend(res)
    # No public ATS API: fresh (48h) LinkedIn guest search at their main hub
    for q, loc, must in [("Data Scientist Booking.com", "Amsterdam, North Holland, Netherlands", "booking"),
                         ("Data Scientist Shopee", "Singapore", "shopee"),
                         ("Data Scientist Zalando", "Berlin, Germany", "zalando"),
                         ("Data Scientist Rakuten", "Tokyo, Japan", "rakuten"),
                         ("Data Scientist Agoda", "Bangkok, Thailand", "agoda"),
                         ("Data Scientist LINE MAN Wongnai", "Bangkok, Thailand", "line man")]:
        res = reloc_tracked("search48h", f"{q} @ {loc.split(',')[0]}", fetch_linkedin_guest, q, loc, target_locs, "r604800")  # past 7 days
        res = [j for j in res if must in j.get("company", "").lower()]  # keep only the named employer
        STATS[-1]["kept"] = len(res)
        discovered.extend(res)

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
        if not is_target_science_role(job.get("job_title", "")) or not JF.title_ok(job.get("job_title", "")):
            continue
        if JF.company_excluded(job.get("company", "")):
            continue
        lo, hi = JF.parse_exp_years(job.pop("_desc", ""))
        if not JF.exp_ok(lo, hi):
            print(f"  - exp filter drop [{job['company']}] {job['job_title']} ({JF.exp_label(lo, hi)})", flush=True)
            continue
        job["_exp_min"], job["_exp_max"] = lo, hi
        job["exp_years"] = JF.exp_label(lo, hi)

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

    print("[sweep_crawler] Per-source results (kept = role+location matches before DB dedupe):", flush=True)
    for st in STATS:
        print(f"  {st['type']:<15} {st['source'][:45]:<45} kept={st['kept']:<3} {('ERROR ' + st['error']) if st['error'] else 'ok'}", flush=True)
    errs = [st for st in STATS if st["error"]]
    print(f"[sweep_crawler] Sources: {len(STATS)} | errors: {len(errs)}", flush=True)
    with open(ROOT_DIR / "job-tracker" / "crawl_stats_latest.json", "w", encoding="utf-8") as f:
        json.dump({"mode": current_mode, "time": datetime.now().strftime("%Y-%m-%d %H:%M IST"), "sources": STATS}, f, indent=2)
    if dry_run:
        print("[sweep_crawler] DRY RUN: not writing found_jobs_latest.json / state.", flush=True)
        return len(to_add)

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
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["existing", "new_companies"], help="Force Run A (existing) or Run B (new_companies)")
    ap.add_argument("--dry-run", action="store_true", help="Do not write found_jobs_latest.json or cron_state.json")
    a = ap.parse_args()
    run_crawler(a.mode, a.dry_run)
