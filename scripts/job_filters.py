"""Shared relevance filters (3-7 yrs experience, top companies, India/UK/AU) + referral defaults."""
import re
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

TITLE_EXCL = [r"\bintern", r"\bgraduate", r"\bjunior", r"\bjr\b", r"\bentry", r"\bassociate", r"\bvice president", r"\bvp\b",
    r"\bdirector", r"\bmanager", r"\bhead\b", r"\bprincipal", r"\bdistinguished",
    r"\bsoftware", r"\bswe\b", r"engineer", r"\bdeveloper", r"devops", r"mlops", r"\bplatform", r"infrastructure",
    r"architect", r"full[- ]?stack", r"front[- ]?end", r"back[- ]?end", r"\bfellow", r"\bphd\b", r"\bpostdoc"]
TITLE_INCL = ["data scientist", "applied scientist", "research scientist", "decision scientist",
    "machine learning scientist", "ml scientist", "data science", "ai scientist", "lead scientist"]

# Chandan 2026-11-01g: hide plain "Data Scientist" (incl. I/II/1/2); keep Senior/Sr/Staff/Lead/III+/Expert etc.
_DS_SENIOR = re.compile(r"\b(senior|snr|sr|staff|lead|expert|specialist|chief)\b")
_DS_LEVEL = re.compile(r"data scientist\s*[-,(]?\s*(iii|iv|v|3|4|5|level\s*[3-9]|l[4-9])\b(?!\s*(to\b|-|\u2013|\+|yr|year|\d))")
def plain_data_scientist(title):
    tl = (title or "").lower()
    if "data scientist" not in tl:
        return False
    if _DS_SENIOR.search(tl) or _DS_LEVEL.search(tl):
        return False
    return True

def title_ok(title):
    tl = (title or "").lower()
    if any(re.search(p, tl) for p in TITLE_EXCL):
        return False
    if plain_data_scientist(title):
        return False
    return any(w in tl for w in TITLE_INCL)

def title_reject_reason(title):
    tl = (title or "").lower()
    for p in TITLE_EXCL:
        if re.search(p, tl):
            return "title seniority/role: " + p.replace("\\b", "")
    if plain_data_scientist(title):
        return "plain Data Scientist title (not Senior/Staff/Lead)"
    if not any(w in tl for w in TITLE_INCL):
        return "title not core DS/Applied Science"
    return ""

# ---- Experience years ----
_RANGE = re.compile(r"(\d{1,2})\s*(?:-|\u2013|\u2014|to)\s*(\d{1,2})\s*\+?\s*(?:years|yrs|year)", re.I)
_MIN = re.compile(r"(?:(?:at least|minimum(?: of)?|min\.?|over)\s*)?(\d{1,2})\s*(\+|plus)?\s*(?:years|yrs|year)", re.I)

def parse_exp_years(text):
    """Return (min, max) or (None, None). Only counts mentions near 'experience'."""
    if not text:
        return None, None
    t = re.sub(r"<[^>]+>", " ", text)
    t = re.sub(r"&nbsp;|&amp;", " ", t)
    cands = []
    for m in _RANGE.finditer(t):
        ctx = t[m.start():m.end() + 80].lower()
        lo, hi = int(m.group(1)), int(m.group(2))
        if "experience" in ctx and 0 < lo <= hi <= 25:
            cands.append((lo, hi))
    for m in _MIN.finditer(t):
        ctx = t[max(0, m.start() - 40):m.end() + 80].lower()
        lo = int(m.group(1))
        if "experience" in ctx and 0 < lo <= 25:
            if any(m.start() >= a.start() and m.end() <= a.end() for a in _RANGE.finditer(t)):
                continue
            cands.append((lo, None))
    if not cands:
        return None, None
    # use the smallest stated minimum (primary requirement)
    cands.sort(key=lambda c: c[0])
    return cands[0]

def exp_label(lo, hi):
    if lo is None:
        return "not stated"
    return f"{lo}-{hi} yrs" if hi is not None else f"{lo}+ yrs"

def exp_ok(lo, hi):
    if lo is None:
        return True
    if lo > 7:
        return False
    if hi is not None and hi < 3:
        return False
    return True

# ---- Companies ----
EXCLUDE_COMPANY = ['accenture', 'antal', 'datatech', 'delta technology', 'epam', 'fractal', 'grid dynamics', 'harnham',
    'inoptra', 'infosys', 'mathco', 'mycareernet', 'nps prism', 'oliver wyman', 'omegahires', 'opus recruitment', 'procdna',
    'recrew', 'sim digital', 'srijan', 'tata consultancy', 'vgreen', 'wipro', 'cognizant', 'ltimindtree', 'tech mahindra',
    'capgemini', 'genpact', 'mu sigma', 'mckinsey', 'bain & company',
    'michael page', 'robert half', 'adecco', 'randstad', 'hays', 'amazon', 'twitch', 'audible', 'zoox', 'whole foods', 'imdb',
    'zappos', 'annapurna labs', 'boston consulting', 'live connections', 'sourcebae', 'ett careermove',
    'rekruton', 'sourcingxpress', 'tibil', 'celebal', 'hcltech', 'birlasoft', 'sigmoid', 'latentview', 'incedo', 'valtech',
    'koantek', 'consulting', 'staffing', 'recruitment', 'consultancy', 'it services', 'global solution centre']
EXCLUDE_SHORT = {'tcs', 'hcl', 'ust', 'bcg', 'bd', 'lmg', 'mvf', 'ets', 'sei', 'bain', 'aws', 'ltts', 'lti',
    'mphasis', 'ltm', 'exl'}

# Deloitte, EY, KPMG, and PwC are allowed. Checked before generic exclusion
# substrings such as "consulting", so "Deloitte Consulting" is not dropped.
_BIG4_RE = re.compile(
    r"(?<![a-z0-9])(?:deloitte|ernst(?:\s+&\s+|\s+and\s+)young|\bey\b|\be\s*&\s*y\b|kpmg|pwc|pricewaterhouse(?:coopers)?)(?![a-z0-9])",
    re.I,
)

def is_big4(company) -> bool:
    return bool(_BIG4_RE.search(_norm(company)))

TOP_COMPANIES = ['openai', 'anthropic', 'google', 'deepmind', 'microsoft', 'meta', 'apple', 'netflix', 'uber', 'snowflake',
    'atlassian', 'flipkart', 'goldman sachs', 'tower research', 'cohere', 'perplexity', 'elevenlabs', 'runway', 'harvey',
    'sarvam', 'scale ai', 'together ai', 'airbnb', 'stripe', 'databricks', 'canva', 'figma', 'deliveroo', 'monzo',
    'tripadvisor', 'affirm', 'wayve', 'revolut', 'wise', 'synthesia', 'servicenow', 'postman', 'spotify', 'inmobi', 'meesho',
    'swiggy', 'zomato', 'eternal', 'blinkit', 'phonepe', 'nvidia', 'adobe', 'salesforce', 'paypal', 'target', 'visa', 'agoda',
    'doordash', 'instacart', 'lyft', 'pinterest', 'reddit', 'roblox', 'duolingo', 'datadog', 'cloudflare', 'mongodb', 'elastic',
    'rubrik', 'razorpay', 'groww', 'browserstack', 'brex', 'ramp', 'notion', 'modal', 'anyscale', 'baseten', 'palantir', 'cred',
    'paytm', 'zeta', 'warner bros', 'expedia', 'snap', 'zepto', 'myntra', 'dream11', 'dream sports', 'makemytrip', 'sharechat',
    'freshworks', 'zoho', 'sprinklr', 'urban company', 'lenskart', 'nykaa', 'delhivery', 'rapido', 'alphagrep', 'graviton',
    'quadeye', 'mistral', 'hugging face', 'krutrim', 'linkedin', 'intuit', 'sap', 'ebay', 'mastercard', 'american express',
    'walmart global tech', 'jiostar', 'jiohotstar', 'hotstar', 'grab', 'coinbase', 'twilio', 'xero', 'trainline', 'navi',
    'zupee', 'redbus', 'scapia', 'navan', 'zillow', 'zip co', 'woven by toyota', 'slice', 'ocado', 'fin', 'nium', 'intel',
    'cisco', 'dolby', 'preply', 'h2o.ai', 'tomtom', 'linktree', 'nike', 'booking', 'shopify', 'square', 'block', 'robinhood',
    'jane street', 'citadel', 'two sigma', 'de shaw', 'd. e. shaw', 'optiver', 'imc', 'jump trading', 'hudson river',
    'qualcomm', 'samsung', 'sony', 'linkedin', 'yahoo', 'oracle', 'workday', 'autodesk', 'dropbox', 'gojek', 'sea limited',
    'shopee', 'thoughtspot', 'glean', 'character.ai', 'xai', 'adept', 'inflection', 'krafton', 'games24x7', 'mpl', 'cars24',
    'ola', 'policybazaar', 'upstox', 'zerodha', 'juspay', 'dunnhumby', 'skyscanner', 'farfetch', 'asos', 'gocardless',
    'checkout.com', 'starling', 'cleo', 'canva', 'airwallex', 'afterpay', 'seek', 'rea group', 'playsimple', 'delivery hero', 'line man wongnai',
    'jpmorgan', 'jpmorganchase', 'jpmorgan chase', 'jp morgan', 'j.p. morgan', 'relay technologies', 'arq', 'quantium',  # restored 2026-11-01e
    'bloomberg', 'noon']  # added 2026-11-01 (Chandan)

def _norm(s):
    return re.sub(r"\s+", " ", (s or "").lower().replace("&amp;", "&")).strip()

def company_excluded(company):
    cl = _norm(company)
    if not cl:
        return True
    if is_big4(cl):
        return False
    if any(ex in cl for ex in EXCLUDE_COMPANY):
        return True
    words = set(re.findall(r"\b[a-z0-9]+\b", cl))
    if any(s in words for s in EXCLUDE_SHORT):
        return True
    return bool(NON_PRODUCT_RE.search(cl))

def company_top(company):
    cl = _norm(company)
    if is_big4(cl):
        return True
    return any(re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", cl) for t in TOP_COMPANIES)

# ---- Service-company gate (Chandan 2026-11-01 rev e: exclude ONLY service-based firms; unknown = product; Big 4 kept) ----
NON_PRODUCT_RE = re.compile(r"(?<![a-z0-9])(" + "|".join([
    # IT services / outsourcing / body-shop / IT & analytics-services consulting / staffing
    r"tcs", r"tata consultancy", r"infosys", r"wipro", r"hcl\w*", r"cognizant", r"capgemini", r"accenture", r"tech mahindra",
    r"ltimindtree", r"lti", r"ltm", r"ltts", r"l ?& ?t", r"larsen", r"globant", r"vysystems", r"ellicium", r"conqueri\w*",
    r"golden opportunities", r"mphasis", r"persistent systems?", r"genpact", r"exl\w*", r"fractal", r"tiger analytics",
    r"mu sigma", r"latentview", r"capco", r"birlasoft", r"epam",
    r"celebal", r"koantek", r"valtech", r"live connections", r"sourcebae", r"sourcingxpress", r"rekruton", r"ett careermove",
    r"tibil", r"data unveil", r"ganit", r"indium", r"kritter", r"qloron", r"relevance lab", r"usefulbi", r"netambit",
    r"trinity life sciences", r"the ai training company",
    # rev f additions (service-based sweep)
    r"global ?logic", r"hitachi digital services", r"thoughtworks", r"nagarro", r"endava", r"virtusa", r"sutherland",
    r"hexaware", r"coforge", r"zensar", r"cyient", r"sonata software", r"mastek", r"ntt data", r"dxc\w*", r"kyndryl",
    r"atos", r"persistent", r"wns", r"firstsource", r"quess", r"randstad", r"adecco", r"manpower\w*", r"hays",
    r"michael page", r"robert walters", r"robert half", r"nigel frank", r"harvey nash", r"experis", r"infoyogi",
    r"ust global", r"ust", r"mindtree", r"igate", r"syntel", r"kpit", r"tata elxsi", r"happiest minds", r"intellect design",
    r"ness digital", r"luxoft", r"softserve", r"ciklum", r"publicis sapient", r"cgi", r"unisys", r"teleperformance",
    r"concentrix", r"ibm consulting", r"harnham", r"antal", r"grid dynamics", r"mathco", r"teksystems", r"kforce",
    r"allegis", r"aerotek", r"collabera", r"insight global", r"talentburst", r"apex systems",
]) + r")(?![a-z0-9])", re.I)

def _load_allow():
    try:
        import json as _j, pathlib as _p
        return [_norm(x) for x in _j.load(open(_p.Path(__file__).with_name("product_companies_allow.json"), encoding="utf-8-sig"))]
    except Exception:
        return []
PRODUCT_ALLOW = _load_allow()

def company_non_product(company):
    if is_big4(company):
        return False
    return bool(NON_PRODUCT_RE.search(_norm(company)))

def company_product(company):
    """True unless the company is service-based (unknown companies assumed product-based)."""
    return not company_non_product(company)

def log_unknown_company(company, title="", loc=""):
    try:
        import pathlib as _p
        lp = _p.Path(__file__).with_name("unknown_company_review.log")
        seen = lp.read_text(encoding="utf-8").lower() if lp.exists() else ""
        if ("| " + _norm(company) + " |") not in seen:
            with open(lp, "a", encoding="utf-8") as f:
                f.write(f"{now_ist()} | {_norm(company)} | {title} | {loc}\n")
    except Exception:
        pass

# ---- Locations ----
_HUBS = ["india", "bangalore", "bengaluru", "hyderabad", "delhi", "gurgaon", "gurugram", "noida", "chennai", "mumbai", "pune",
    "kolkata", "london", "england", "united kingdom", "great britain", "cambridge", "sydney", "melbourne", "australia",
    "remote (uk)", "frontier ai lab hubs (us/uk",
    "bangkok", "thailand", "dubai", "united arab emirates", "uae"]  # Thailand + UAE approved by Chandan 2026-10-30
_NON_TARGET = ["united states", "usa", " us", "canada", "san francisco", "new york", "seattle", ", ca", "remote us"]


# Chandan 2026-11-01: no Pune / Chennai / West Bengal / Tamil Nadu jobs. Multi-location listings that also
# name an allowed city (e.g. Bengaluru) are kept.
_BLOCKED_LOC_RE = re.compile(r"pune|pimpri|chinchwad|hinjewadi|chennai|madras|west bengal|kolkata|calcutta|howrah|durgapur|siliguri|"
    r"tamil ?nadu|\btn\b|coimbatore|madurai|tiruchirappalli|trichy|hosur|sriperumbudur|kanchipuram|vellore|salem|tirupur|erode", re.I)
_GENERIC_LOC_RE = re.compile(r"\b(india|in|maharashtra|area|division|city|metropolitan|metro|greater|region|district|remote|hybrid|on-?site)\b", re.I)
def loc_blocked(loc):
    ll = (loc or "").lower()
    if not _BLOCKED_LOC_RE.search(ll):
        return False
    rest = _GENERIC_LOC_RE.sub(" ", _BLOCKED_LOC_RE.sub(" ", ll))
    return re.sub(r"[^a-z]", "", rest) == ""

def location_ok(loc):
    ll = _norm(loc)
    if not ll:
        return True
    if loc_blocked(loc):
        return False
    if any(h in ll for h in _HUBS) or re.search(r"\b(uk|gb|nsw|vic|th|ae)\b", ll):
        return True
    if "remote" in ll:
        rest = re.sub(r"remote|global|worldwide|anywhere|apac|emea|[^a-z]", "", ll)
        return rest == ""
    return False

def visibility(job, require_top=True):
    """Return (visible, reason). require_top=False is used for the Other companies section."""
    if (job.get("status") or "").lower() == "applied":
        return True, ""
    if (job.get("referral") or {}).get("status", "none") not in ("none", None):
        return True, ""  # active referral pipeline stays visible
    if company_excluded(job.get("company")):
        return False, "company excluded (consultancy/staffing/IT services/Amazon)"
    if require_top and not company_top(job.get("company")):
        return False, "company not in top-tier list"
    if not require_top and not company_product(job.get("company")):
        return False, "service-based company"
    r = title_reject_reason(job.get("job_title"))
    if r:
        return False, r
    if not location_ok(job.get("location")):
        return False, "location outside India/UK/Australia/Thailand/UAE"
    lo, hi = job.get("_exp_min"), job.get("_exp_max")
    if not exp_ok(lo, hi):
        return False, f"experience requirement {exp_label(lo, hi)} outside 3-7 yrs"
    return True, ""

def default_referral():
    return {"status": "none", "contacts": [], "updated_at": None}

def ensure_fields(job):
    """Add new fields without dropping anything."""
    job.setdefault("exp_years", "not stated")
    if not isinstance(job.get("referral"), dict):
        job["referral"] = default_referral()
    else:
        for k, v in default_referral().items():
            job["referral"].setdefault(k, v)
    if "dashboard_visible" not in job or job.get("_recheck"):
        vis, why = visibility(job)
        job["dashboard_visible"], job["hide_reason"] = vis, why
    job.pop("_recheck", None)
    return job

def now_ist():
    return datetime.now(IST).isoformat(timespec="minutes")


def tier(job):
    """'top' for top-tier companies, 'other' for non-top companies that pass every other filter."""
    return "top" if company_top(job.get("company")) else "other"
