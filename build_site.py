"""
Build Site Generator
====================
Reads tracked_jobs.json (or found_jobs_latest.json) and compiles:
1. data/jobs.json
2. index.html (self-contained, responsive dashboard with embedded dataset, Chart.js,
   and interactive local application tracking via localStorage)

Run with:
    python build_site.py
"""

import json
import re
from pathlib import Path
from datetime import datetime, timezone

PROJECT_DIR = Path(__file__).parent
DATA_DIR    = PROJECT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

TRACKED_PATH = Path(r"C:\Users\chand\Downloads\Job Search\job-tracker\tracked_jobs.json")
if not TRACKED_PATH.exists():
    TRACKED_PATH = Path(r"C:\Users\chand\Downloads\Job Search\job-tracker\found_jobs_latest.json")

CONFIG_PATH = Path(r"C:\Users\chand\Downloads\Job Search\job-tracker\config.json")

def load_user_profile():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
            return cfg.get("user_profile", {})
    return {}

def load_jobs_data():
    with open(TRACKED_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("all_jobs", []), data.get("applied", []), data.get("skipped", [])
    return data, [], []

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

SHORT_EXCLUSIONS = {'ey', 'tcs', 'pwc', 'hcl', 'ust', 'bcg', 'bd', 'lmg', 'mvf'}

def is_top_product_company(company: str) -> bool:
    cl = company.lower().strip()
    if not cl:
        return False
    if any(ex in cl for ex in PHRASE_EXCLUSIONS_LOWER):
        return False
    words = set(re.findall(r'\b[a-z0-9]+\b', cl))
    if any(short in words for short in SHORT_EXCLUSIONS):
        return False
    return True

def is_pure_science_role(title: str) -> bool:
    tl = title.lower()
    if any(w in tl for w in ["principal", "staff", "intern", "graduate", "junior", "entry", "vice president", "director"]):
        return False
    if any(w in tl for w in ["software", "engineer", "engineering", "developer", "devops", "mlops", "platform", "infrastructure", "architect"]):
        return False
    return any(w in tl for w in ["data scientist", "applied scientist", "research scientist", "decision scientist", "machine learning scientist", "ml scientist", "data science"])

import sys as _sys
_sys.path.insert(0, r"C:\Users\chand\Downloads\Job Search\job-tracker")
import job_filters as JF

def build_dashboard():
    try:
        import merge_referral_updates as _MRU
        _MRU.main()
    except Exception as _e:
        print(f"[build_site] referral merge skipped: {_e}")

    raw_jobs, db_applied, db_skipped = load_jobs_data()
    uprofile = load_user_profile()
    user_name = uprofile.get("name", "Chandan Malla")
    user_email = uprofile.get("email", "chandanmalla@gmail.com")
    user_phone = uprofile.get("phone", "[Phone Number]")
    now_ist = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M IST")

    jobs = []
    for idx, j in enumerate(raw_jobs, start=1):
        company = j.get("company", "")
        title = j.get("job_title", "")
        # Strictly require Top Product Companies and Data Science / Applied Science
        JF.ensure_fields(j)  # adds exp_years / referral / dashboard_visible if missing (in-memory only)
        if not j.get("dashboard_visible", True) and (j.get("status") or "").lower() != "applied":
            continue

        loc = j.get("location", "")
        country = "India" if any(w in loc.lower() for w in ["india", "bangalore", "bengaluru", "hyderabad", "delhi", "gurgaon", "gurugram", "noida", "mumbai", "chennai", "pune"]) \
            else "UK" if any(w in loc.lower() for w in ["uk", "london", "united kingdom", "england", "cambridge"]) \
            else "Australia" if any(w in loc.lower() for w in ["australia", "sydney", "melbourne"]) \
            else "Global / Other"

        city = "Bangalore" if "bangalore" in loc.lower() or "bengaluru" in loc.lower() \
            else "Hyderabad" if "hyderabad" in loc.lower() \
            else "Delhi NCR" if any(w in loc.lower() for w in ["delhi", "gurgaon", "gurugram", "noida"]) \
            else "Mumbai" if "mumbai" in loc.lower() \
            else "Pune" if "pune" in loc.lower() \
            else "Chennai" if "chennai" in loc.lower() \
            else "Melbourne" if "melbourne" in loc.lower() \
            else "London" if "london" in loc.lower() \
            else "Sydney" if "sydney" in loc.lower() \
            else loc

        visa_raw = j.get("visa_sponsorship", "Unknown")
        visa_cat = "Confirmed" if "confirmed" in visa_raw.lower() \
            else "Plausible but unverified" if "plausible" in visa_raw.lower() \
            else "N/A (India role)" if "n/a" in visa_raw.lower() or country == "India" \
            else "Unknown"

        exp_raw = j.get("experience_fit", "Good fit")
        exp_cat = "Strong" if "strong" in exp_raw.lower() \
            else "Stretch" if "stretch" in exp_raw.lower() or j.get("stretch") \
            else "Good"

        jobs.append({
            "id": j.get("job_id", f"J{idx:03d}"),
            "company": j.get("company", ""),
            "title": j.get("job_title", ""),
            "location": loc,
            "city": city,
            "country": country,
            "posted": j.get("date_posted", "Unverified"),
            "exp": exp_raw,
            "expCat": exp_cat,
            "tech": j.get("technical_fit", ""),
            "visa": visa_raw,
            "visaCat": visa_cat,
            "reloc": j.get("relocation", "Not stated"),
            "link": j.get("link", ""),
            "source": j.get("source", ""),
            "why_fits": j.get("why_fits", ""),
            "isNew": True,
            "expYears": j.get("exp_years", "not stated"),
            "referral": j.get("referral") or JF.default_referral()
        })

    # Save to data/jobs.json
    out_json = DATA_DIR / "jobs.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(jobs)} jobs to {out_json}")

    jobs_embed = json.dumps(jobs, ensure_ascii=False).replace("</", "<\\/")
    # Build HTML Dashboard
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ML & Data Science Job Tracker | Live Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --navy: #0f172a;
      --primary: #1e40af;
      --primary-light: #3b82f6;
      --border: #e2e8f0;
      --text-main: #0f172a;
      --text-muted: #64748b;
      --green: #10b981;
      --green-bg: #ecfdf5;
      --amber: #f59e0b;
      --amber-bg: #fffbeb;
      --rose: #ef4444;
      --rose-bg: #fef2f2;
      --purple: #8b5cf6;
      --purple-bg: #f5f3ff;
      --blue-bg: #eff6ff;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text-main);
      line-height: 1.5;
    }}
    header {{
      background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
      color: #fff;
      padding: 24px 32px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }}
    .header-content {{
      max-width: 1400px;
      margin: 0 auto;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }}
    header h1 {{
      font-size: 24px;
      font-weight: 700;
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    header p {{
      color: #94a3b8;
      font-size: 13px;
      margin-top: 4px;
    }}
    .refresh-badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(255,255,255,0.1);
      border: 1px solid rgba(255,255,255,0.2);
      border-radius: 999px;
      padding: 6px 14px;
      font-size: 12px;
      color: #e2e8f0;
    }}
    .pulse {{
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #10b981;
      box-shadow: 0 0 8px #10b981;
    }}
    main {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 24px 32px;
    }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin-bottom: 24px;
    }}
    .kpi-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 20px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .kpi-card .lbl {{
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .kpi-card .val {{
      font-size: 28px;
      font-weight: 700;
      color: var(--text-main);
      margin-top: 6px;
    }}
    .kpi-card.highlight {{
      border-left: 4px solid var(--primary-light);
    }}
    .kpi-card.applied-kpi {{
      border-left: 4px solid var(--green);
      background: #f0fdf4;
    }}
    .charts-grid {{
      display: grid;
      grid-template-columns: 2fr 1fr 1fr;
      gap: 16px;
      margin-bottom: 24px;
    }}
    @media (max-width: 1024px) {{
      .charts-grid {{ grid-template-columns: 1fr; }}
    }}
    .chart-box {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 18px 20px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }}
    .chart-box h3 {{
      font-size: 14px;
      font-weight: 600;
      color: var(--text-main);
      margin-bottom: 14px;
    }}
    .chart-container {{
      position: relative;
      height: 240px;
    }}
    .table-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
      overflow: hidden;
    }}
    .filter-bar {{
      padding: 18px 20px;
      border-bottom: 1px solid var(--border);
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      background: #fafafa;
    }}
    .search-input {{
      flex: 1;
      min-width: 220px;
      padding: 9px 14px;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 13px;
      background: #fff;
    }}
    .search-input:focus, select:focus {{
      outline: none;
      border-color: var(--primary-light);
      box-shadow: 0 0 0 2px rgba(59,130,246,0.15);
    }}
    select {{
      padding: 9px 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 13px;
      background: #fff;
      color: var(--text-main);
      cursor: pointer;
    }}
    .status-select {{
      font-weight: 600;
      border-color: #cbd5e1;
      background: #f8fafc;
    }}
    .btn-action {{
      padding: 9px 14px;
      background: #fff;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      color: var(--text-muted);
      transition: all 0.15s;
    }}
    .btn-action:hover {{
      background: #f1f5f9;
      color: var(--text-main);
    }}
    .counter-tag {{
      margin-left: auto;
      font-size: 13px;
      font-weight: 600;
      color: var(--text-muted);
    }}
    .table-container {{
      overflow-x: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 13px;
      min-width: 1250px;
    }}
    th {{
      background: #f8fafc;
      padding: 12px 14px;
      font-weight: 600;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
      cursor: pointer;
      user-select: none;
    }}
    th:hover {{
      background: #f1f5f9;
    }}
    td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }}
    tr:hover td {{
      background: #f8fafc;
    }}
    tr.is-applied td {{
      background: #f0fdf4 !important;
    }}
    tr.is-skipped td {{
      opacity: 0.45;
    }}
    .job-title {{
      font-weight: 600;
      color: var(--navy);
      display: block;
      margin-bottom: 2px;
    }}
    .company-cell {{
      font-weight: 600;
      white-space: nowrap;
    }}
    .badge {{
      display: inline-block;
      padding: 3px 8px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 600;
      white-space: nowrap;
    }}
    .badge-confirmed {{ background: var(--green-bg); color: #065f46; border: 1px solid rgba(16,185,129,0.2); }}
    .badge-plausible {{ background: var(--amber-bg); color: #92400e; border: 1px solid rgba(245,158,11,0.2); }}
    .badge-na {{ background: var(--blue-bg); color: #1e40af; border: 1px solid rgba(59,130,246,0.2); }}
    .badge-unknown {{ background: #f1f5f9; color: #475569; }}
    .badge-strong {{ background: var(--green-bg); color: #065f46; }}
    .badge-good {{ background: var(--blue-bg); color: #1e40af; }}
    .badge-stretch {{ background: var(--amber-bg); color: #92400e; }}
    .btn-apply {{
      display: inline-block;
      padding: 6px 12px;
      background: var(--primary);
      color: #fff;
      border-radius: 6px;
      font-weight: 600;
      font-size: 12px;
      text-decoration: none;
      transition: background 0.15s;
      white-space: nowrap;
      text-align: center;
    }}
    .btn-apply:hover {{
      background: #1e3a8a;
    }}
    .btn-referral {{
      display: inline-block;
      padding: 5px 8px;
      background: #f8fafc;
      color: #0f172a;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      font-weight: 600;
      font-size: 11px;
      cursor: pointer;
      transition: all 0.15s;
      white-space: nowrap;
      text-align: center;
    }}
    .btn-referral:hover {{
      background: #e2e8f0;
      color: #1e40af;
      border-color: #93c5fd;
    }}
    .btn-track {{
      padding: 5px 10px;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      background: #fff;
      color: var(--text-muted);
      transition: all 0.15s;
      white-space: nowrap;
    }}
    .btn-track:hover {{
      background: #f1f5f9;
      color: var(--text-main);
    }}
    .btn-track.applied {{
      background: var(--green);
      color: #fff;
      border-color: var(--green);
    }}
    .btn-icon {{
      border: none;
      background: transparent;
      cursor: pointer;
      font-size: 14px;
      color: #94a3b8;
      padding: 4px;
      border-radius: 4px;
    }}
    .btn-icon:hover {{
      color: #ef4444;
      background: #fee2e2;
    }}
    .action-group {{
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .sub-text {{
      font-size: 11px;
      color: var(--text-muted);
      margin-top: 3px;
    }}
    footer {{
      text-align: center;
      padding: 32px;
      color: var(--text-muted);
      font-size: 13px;
    }}
    /* ===== Dark-mode-first theme (toggle to light; choice saved in localStorage) ===== */
    html:not(.light) {{ --bg:#0b1120; --card-bg:#111827; --border:#1f2937; --text-main:#e5e7eb; --text-muted:#94a3b8;
      --green-bg:#052e1f; --amber-bg:#2b1d05; --rose-bg:#2a0f12; --purple-bg:#1e1636; --blue-bg:#0c1a33; color-scheme: dark; }}
    html:not(.light) body {{ background:var(--bg); color:var(--text-main); }}
    html:not(.light) .kpi-card, html:not(.light) .chart-box, html:not(.light) .table-card, html:not(.light) table,
    html:not(.light) thead th, html:not(.light) td, html:not(.light) .filter-bar, html:not(.light) select,
    html:not(.light) input, html:not(.light) .btn-action, html:not(.light) .btn-referral, html:not(.light) .btn-icon,
    html:not(.light) .btn-track, html:not(.light) .modal, html:not(.light) .modal-content, html:not(.light) .badge-unknown
      {{ background:var(--card-bg) !important; color:var(--text-main) !important; border-color:var(--border) !important; }}
    html:not(.light) tr:hover td {{ background:#162033 !important; }}
    html:not(.light) tr.is-applied td {{ background:#06281b !important; }}
    html:not(.light) .job-title, html:not(.light) .company-cell, html:not(.light) .val {{ color:#f8fafc !important; }}
    html:not(.light) .btn-track.applied {{ background:#065f46 !important; color:#d1fae5 !important; }}
    tr.is-skipped td {{ opacity:.45; }}
    .snip-row {{ display:flex; gap:4px; flex-wrap:wrap; }}
    .btn-snip {{ font-size:11px; padding:3px 7px; border-radius:6px; border:1px solid var(--border); background:var(--card-bg); color:var(--text-main); cursor:pointer; }}
    .btn-snip:hover {{ border-color:var(--primary-light); }}
    #btnTheme {{ position:fixed; right:14px; bottom:14px; z-index:50; padding:8px 12px; border-radius:999px; border:1px solid var(--border); background:var(--card-bg); color:var(--text-main); cursor:pointer; }}
    @media (max-width: 760px) {{ .table-container {{ overflow-x:auto; }} .kpi-grid {{ grid-template-columns: repeat(2, 1fr) !important; }} }}
  </style>
  <script>if (localStorage.getItem('theme') === 'light') document.documentElement.classList.add('light');</script>
</head>
<body>
  <header>
    <div class="header-content">
      <div>
        <h1>🎯 Machine Learning & Data Science Job Tracker</h1>
        <p>Curated verified-open roles (Senior, Lead, Applied Scientist) across India, UK & Australia</p>
      </div>
      <div class="refresh-badge">
        <span class="pulse"></span> Last Updated: {now_ist}
      </div>
    </div>
  </header>

  <main>
    <section class="kpi-grid">
      <div class="kpi-card highlight">
        <div class="lbl">Total Active Roles</div>
        <div class="val" id="kpiTotal">0</div>
      </div>
      <div class="kpi-card applied-kpi">
        <div class="lbl">Applied by You</div>
        <div class="val" id="kpiApplied">0</div>
      </div>
      <div class="kpi-card">
        <div class="lbl">Backlog / Pending</div>
        <div class="val" id="kpiBacklog">0</div>
      </div>
      <div class="kpi-card">
        <div class="lbl">India Roles</div>
        <div class="val" id="kpiIndia">0</div>
      </div>
      <div class="kpi-card">
        <div class="lbl">UK Roles</div>
        <div class="val" id="kpiUK">0</div>
      </div>
      <div class="kpi-card">
        <div class="lbl">Australia Roles</div>
        <div class="val" id="kpiAU">0</div>
      </div>
      <div class="kpi-card">
        <div class="lbl">Referred</div>
        <div class="val" id="kpiReferred">0</div>
      </div>
      <div class="kpi-card">
        <div class="lbl">Needs Direct Apply</div>
        <div class="val" id="kpiDirect">0</div>
      </div>
      <div class="kpi-card">
        <div class="lbl">Target Companies</div>
        <div class="val" id="kpiCompanies">0</div>
      </div>
    </section>

    <section class="charts-grid">
      <div class="chart-box">
        <h3>Top Hiring Companies</h3>
        <div class="chart-container"><canvas id="chartCompany"></canvas></div>
      </div>
      <div class="chart-box">
        <h3>Roles by Location</h3>
        <div class="chart-container"><canvas id="chartLocation"></canvas></div>
      </div>
      <div class="chart-box">
        <h3>Visa Sponsorship Status</h3>
        <div class="chart-container"><canvas id="chartVisa"></canvas></div>
      </div>
    </section>

    <section class="table-card">
      <div class="filter-bar">
        <input type="search" id="searchQ" class="search-input" placeholder="🔍 Search company, role title, skills, ID…">
        <select id="selStatus" class="status-select">
          <option value="all">All Roles</option>
          <option value="unapplied" selected>Unapplied (Active)</option>
          <option value="applied">Applied Only (Tracker)</option>
          <option value="skipped">Skipped / Hidden</option>
        </select>
        <select id="selCountry"><option value="">All Countries</option></select>
        <select id="selCity"><option value="">All Locations</option></select>
        <select id="selCompany"><option value="">All Companies</option></select>
        <select id="selVisa"><option value="">All Sponsorship</option></select>
        <select id="selExp"><option value="">All Experience Fit</option></select>
        <select id="selReferral"><option value="">Referral: All</option><option value="referred">Referred</option><option value="pending">Requested / Reminded</option><option value="apply_direct">Apply direct</option><option value="none">None</option></select>
        <button class="btn-action" id="btnCopyApplied" title="Copy comma-separated list of your applied Job IDs">📋 Copy IDs</button>
        <button class="btn-action" id="btnSyncTelegram" style="background:#0284c7;color:#fff;border-color:#0284c7;font-weight:600;" title="Open Telegram with pre-filled /applied command for all your marked jobs">📲 Sync to Telegram</button>
        <button class="btn-action" id="btnEditContact" title="Update your name, phone number, and email for referral messages">⚙️ My Contact Info</button>
        <button class="btn-action" id="btnReset">Reset</button>
        <span class="counter-tag" id="rowCounter">0 roles</span>
      </div>

      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th onclick="sortTable('id')">ID</th>
              <th>My Status</th>
              <th onclick="sortTable('company')">Company</th>
              <th onclick="sortTable('title')">Job Title</th>
              <th onclick="sortTable('city')">Location</th>
              <th onclick="sortTable('expCat')">Fit</th>
              <th>Technical Match</th>
              <th onclick="sortTable('visaCat')">Visa Sponsorship</th>
              <th>Application</th>
            </tr>
          </thead>
          <tbody id="jobsTbody"></tbody>
        </table>
      </div>
    </section>
  </main>

  <footer>
    <p>Curated automatically every 2 hours &middot; Top Product Companies in India & Globally &middot; Core Data Science & Applied Science roles &middot; Consultancies, Services & Amazon strictly excluded</p>
  </footer>


  <script id="jobs-data" type="application/json">{jobs_embed}</script>

  <script>
    const JOBS = JSON.parse(document.getElementById('jobs-data').textContent);
    const DB_APPLIED = {json.dumps(db_applied)};
    const DB_SKIPPED = {json.dumps(db_skipped)};

    // Persistent storage for Applied & Skipped jobs, merging DB state + browser localStorage
    let appliedJobs = new Set([...DB_APPLIED, ...JSON.parse(localStorage.getItem('applied_jobs') || '[]')]);
    let skippedJobs = new Set([...DB_SKIPPED, ...JSON.parse(localStorage.getItem('skipped_jobs') || '[]')]);

    // Referral status: DB value, overridden by manual "Mark Referred" saved in localStorage
    let referredLocal = new Set(JSON.parse(localStorage.getItem('referred_jobs') || '[]'));
    const REF_COLORS = {{none:'#64748b', requested:'#0284c7', reminded:'#7c3aed', referred:'#16a34a', no_response:'#d97706', apply_direct:'#dc2626'}};
    const REF_LABELS = {{none:'No referral', requested:'Referral requested', reminded:'Reminded', referred:'Referred', no_response:'No response', apply_direct:'Apply direct'}};
    function refStatus(j) {{ return referredLocal.has(j.id) ? 'referred' : ((j.referral && j.referral.status) || 'none'); }}
    function refBadge(j) {{
      const s = refStatus(j); const n = (j.referral && j.referral.contacts || []).length;
      const tip = (j.referral && j.referral.contacts || []).map(c => c.name + (c.first_message_at ? ' (msg ' + c.first_message_at.slice(0,16).replace('T',' ') + ')' : '')).join(', ');
      return `<span class="badge" title="${{tip}}" style="background:${{REF_COLORS[s]||'#64748b'}};color:#fff;">🤝 ${{REF_LABELS[s]||s}}${{n ? ' · ' + n : ''}}</span>`;
    }}
    window.toggleReferred = function(id) {{
      if (referredLocal.has(id)) referredLocal.delete(id); else referredLocal.add(id);
      localStorage.setItem('referred_jobs', JSON.stringify([...referredLocal]));
      updateStats(); renderTable();
    }};
    let refFilter = '';

    let state = {{
      search: '',
      status: 'unapplied',
      country: '',
      city: '',
      company: '',
      visa: '',
      exp: '',
      sortKey: 'id',
      sortAsc: true
    }};

    function updateStats() {{
      document.getElementById('kpiTotal').textContent = JOBS.length;
      document.getElementById('kpiApplied').textContent = appliedJobs.size;
      document.getElementById('kpiIndia').textContent = JOBS.filter(j => j.country === 'India').length;
      document.getElementById('kpiUK').textContent = JOBS.filter(j => j.country === 'UK').length;
      document.getElementById('kpiAU').textContent = JOBS.filter(j => j.country === 'Australia').length;
      document.getElementById('kpiBacklog').textContent = JOBS.filter(j => !appliedJobs.has(j.id) && !skippedJobs.has(j.id)).length;
      document.getElementById('kpiReferred').textContent = JOBS.filter(j => refStatus(j) === 'referred').length;
      document.getElementById('kpiDirect').textContent = JOBS.filter(j => ['apply_direct','no_response'].includes(refStatus(j)) && !appliedJobs.has(j.id)).length;
      document.getElementById('kpiCompanies').textContent = new Set(JOBS.map(j => j.company)).size;
    }}

    updateStats();

    // Populate dropdowns
    function populateFilter(id, items) {{
      const el = document.getElementById(id);
      const unique = [...new Set(items.filter(Boolean))].sort();
      unique.forEach(item => {{
        const opt = document.createElement('option');
        opt.value = item;
        opt.textContent = item;
        el.appendChild(opt);
      }});
    }}

    populateFilter('selCountry', JOBS.map(j => j.country));
    populateFilter('selCity', JOBS.map(j => j.city));
    populateFilter('selCompany', JOBS.map(j => j.company));
    populateFilter('selVisa', JOBS.map(j => j.visaCat));
    populateFilter('selExp', JOBS.map(j => j.expCat));

    // Render Table
    function renderTable() {{
      const tbody = document.getElementById('jobsTbody');
      const filtered = JOBS.filter(j => {{
        const q = state.search.toLowerCase();
        const matchesQ = !q || (j.company + ' ' + j.title + ' ' + j.location + ' ' + j.tech + ' ' + j.id).toLowerCase().includes(q);
        const matchesCountry = !state.country || j.country === state.country;
        const matchesCity = !state.city || j.city === state.city;
        const matchesCompany = !state.company || j.company === state.company;
        const matchesVisa = !state.visa || j.visaCat === state.visa;
        const matchesExp = !state.exp || j.expCat === state.exp;

        const isApplied = appliedJobs.has(j.id);
        const isSkipped = skippedJobs.has(j.id);

        let matchesStatus = true;
        if (state.status === 'unapplied') {{
          matchesStatus = !isApplied && !isSkipped;
        }} else if (state.status === 'applied') {{
          matchesStatus = isApplied;
        }} else if (state.status === 'skipped') {{
          matchesStatus = isSkipped;
        }}

        const rs = refStatus(j);
        const matchesRef = !refFilter || (refFilter === 'pending' ? (rs === 'requested' || rs === 'reminded') : refFilter === 'apply_direct' ? (rs === 'apply_direct' || rs === 'no_response') : rs === refFilter);
        if (!matchesRef) return false;
        return matchesQ && matchesCountry && matchesCity && matchesCompany && matchesVisa && matchesExp && matchesStatus;
      }});

      filtered.sort((a, b) => {{
        let vA = a[state.sortKey] || '';
        let vB = b[state.sortKey] || '';
        if (typeof vA === 'string') vA = vA.toLowerCase();
        if (typeof vB === 'string') vB = vB.toLowerCase();
        return (vA < vB ? -1 : vA > vB ? 1 : 0) * (state.sortAsc ? 1 : -1);
      }});

      document.getElementById('rowCounter').textContent = `${{filtered.length}} of ${{JOBS.length}} roles`;

      tbody.innerHTML = filtered.map(j => {{
        const isApplied = appliedJobs.has(j.id);
        const isSkipped = skippedJobs.has(j.id);

        const vClass = j.visaCat === 'Confirmed' ? 'badge-confirmed' :
                       j.visaCat.includes('Plausible') ? 'badge-plausible' :
                       j.visaCat.includes('N/A') ? 'badge-na' : 'badge-unknown';

        const eClass = j.expCat === 'Strong' ? 'badge-strong' :
                       j.expCat === 'Stretch' ? 'badge-stretch' : 'badge-good';

        const applyBtn = j.link && j.link.startsWith('http')
          ? `<a href="${{j.link}}" target="_blank" rel="noopener" class="btn-apply">Direct Apply ↗</a>`
          : `<span class="sub-text">Unverified</span>`;

        const trackBtn = isApplied
          ? `<button class="btn-track applied" onclick="toggleApplied('${{j.id}}')">Applied ✅</button>`
          : `<button class="btn-track" onclick="toggleApplied('${{j.id}}')">Mark Applied</button>`;

        const skipBtn = isSkipped
          ? `<button class="btn-icon" title="Restore role" onclick="toggleSkipped('${{j.id}}')">↩️</button>`
          : `<button class="btn-icon" title="Not interested / Hide" onclick="toggleSkipped('${{j.id}}')">✕</button>`;

        const rowClass = isApplied ? 'is-applied' : isSkipped ? 'is-skipped' : '';

        return `
          <tr class="${{rowClass}}">
            <td><code>${{j.id}}</code></td>
            <td>
              <div class="action-group">
                ${{trackBtn}}
                ${{skipBtn}}
                <button class="btn-track" style="${{refStatus(j)==='referred' ? 'background:#16a34a;color:#fff;' : ''}}" onclick="toggleReferred('${{j.id}}')" title="Manually mark that someone referred you">${{refStatus(j)==='referred' ? 'Referred 🤝' : 'Mark Referred'}}</button>
              </div>
              <div style="margin-top:4px">${{refBadge(j)}}</div>
            </td>
            <td class="company-cell">${{j.company}}</td>
            <td>
              <span class="job-title">${{j.title}}</span>
              <div class="sub-text">📅 ${{j.posted}} · 🎓 Exp: ${{j.expYears || 'not stated'}}</div>
            </td>
            <td>
              <div>${{j.city}}</div>
              <div class="sub-text">${{j.country}}</div>
            </td>
            <td><span class="badge ${{eClass}}">${{j.expCat}}</span></td>
            <td>
              <div>${{j.tech}}</div>
            </td>
            <td><span class="badge ${{vClass}}">${{j.visaCat}}</span></td>
            <td>
              <div style="display:flex;flex-direction:column;gap:5px;">
                ${{applyBtn}}
                <div class="snip-row">
                  <button class="btn-snip" onclick="copySnippet('${{j.id}}','summary')" title="Copy tailored summary">📋 Summary</button>
                  <button class="btn-snip" onclick="copySnippet('${{j.id}}','fit')" title="Copy why I fit">📋 Why I fit</button>
                  <button class="btn-snip" onclick="copySnippet('${{j.id}}','pitch')" title="Copy quick pitch">📋 Pitch</button>
                </div>
                <button class="btn-referral" onclick="copyReferral('${{j.id}}')" title="Copy personalized LinkedIn referral message">💬 Referral Note</button>
              </div>
            </td>
          </tr>
        `;
      }}).join('');
    }}

    // Toggle Applied state (persists in localStorage)
    window.toggleApplied = function(id) {{
      if (appliedJobs.has(id)) {{
        appliedJobs.delete(id);
      }} else {{
        appliedJobs.add(id);
        skippedJobs.delete(id);
      }}
      localStorage.setItem('applied_jobs', JSON.stringify([...appliedJobs]));
      localStorage.setItem('skipped_jobs', JSON.stringify([...skippedJobs]));
      updateStats();
      renderTable();
    }};

    // Toggle Skipped state (persists in localStorage)
    window.toggleSkipped = function(id) {{
      if (skippedJobs.has(id)) {{
        skippedJobs.delete(id);
      }} else {{
        skippedJobs.add(id);
        appliedJobs.delete(id);
      }}
      localStorage.setItem('applied_jobs', JSON.stringify([...appliedJobs]));
      localStorage.setItem('skipped_jobs', JSON.stringify([...skippedJobs]));
      updateStats();
      renderTable();
    }};

    // One-click tailored application snippets
    function buildSnippet(j, kind) {{
      const tech = j.tech || 'statistical modeling, experimentation, causal inference and ML';
      if (kind === 'summary') return `Senior Data / Applied Scientist with ~5 years building production ML and statistical models end to end (Python, SQL, PyTorch). Experienced in ${{tech}}, translating ambiguous business problems into measurable model and product impact. Excited by the ${{j.title}} role at ${{j.company}} (${{j.location}}).`;
      if (kind === 'fit') return `Why I fit ${{j.company}} - ${{j.title}}:\n- ~5 years of hands-on data science / applied science, matching the role's seniority\n- Depth in ${{tech}}\n- Track record of shipping models to production and measuring impact with A/B tests\n- ${{j.why_fits || 'Strong alignment with the core science scope of this team'}}`;
      return `Hi! I'm a Senior Data Scientist (~5 yrs; ${{tech.split(',').slice(0,3).join(', ')}}) and I'd love to be considered for ${{j.title}} at ${{j.company}}. I've shipped ML that moved core product metrics and would bring that to your team. Happy to share details. ${{j.link || ''}}`;
    }}
    window.copySnippet = function(id, kind) {{
      const j = JOBS.find(x => x.id === id); if (!j) return;
      const text = buildSnippet(j, kind);
      const done = () => {{ const t = document.getElementById('toast'); if (t) {{ t.textContent = 'Copied ' + kind + ' for ' + j.company; t.style.opacity = 1; setTimeout(() => t.style.opacity = 0, 1600); }} }};
      if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done);
      else {{ const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove(); done(); }}
    }};
    document.addEventListener('DOMContentLoaded', () => {{
      const b = document.createElement('button'); b.id = 'btnTheme';
      const label = () => b.textContent = document.documentElement.classList.contains('light') ? '🌙 Dark' : '☀️ Light';
      label(); b.onclick = () => {{ document.documentElement.classList.toggle('light'); localStorage.setItem('theme', document.documentElement.classList.contains('light') ? 'light' : 'dark'); label(); }};
      document.body.appendChild(b);
      const t = document.createElement('div'); t.id = 'toast'; t.style.cssText = 'position:fixed;left:50%;bottom:18px;transform:translateX(-50%);background:#10b981;color:#fff;padding:8px 14px;border-radius:8px;opacity:0;transition:opacity .3s;z-index:60;font-size:13px';
      document.body.appendChild(t);
    }});

    // Copy personalized, professionally formatted LinkedIn referral message
    window.copyReferral = function(id) {{
      const j = JOBS.find(item => item.id === id);
      if (!j) return;
      const link = j.link && j.link.startsWith('http') ? j.link : '';
      const focus = j.tech ? (j.tech.length > 85 ? j.tech.slice(0, 85) + '...' : j.tech) : 'recommender systems, LLMs & MLOps';

      const savedName = localStorage.getItem('user_name') || '{user_name}';
      const savedPhone = localStorage.getItem('user_phone') || '{user_phone}';
      const savedEmail = localStorage.getItem('user_email') || '{user_email}';

      const note = `Hi [Name],

I hope you're having a great week!

I noticed an open ${{j.title}} role at ${{j.company}}:
${{link}}

With ~6 years of experience in Machine Learning & Data Science (specializing in Python, PyTorch, Recommender Systems, LLMs/GenAI, and MLOps), my background in ${{focus}} aligns closely with the role requirements.

Would you be open to connecting or referring me for this position? I would really appreciate it!

Best regards,
${{savedName}}
📱 Phone: ${{savedPhone}}
✉️ Email: ${{savedEmail}}`;

      navigator.clipboard.writeText(note).then(() => {{
        alert(`📋 Formatted LinkedIn Referral Message copied to clipboard for ${{j.company}}!\\n\\n${{note}}\\n\\nReady to paste directly into LinkedIn.`);
      }}).catch(() => {{
        prompt("Copy your LinkedIn Referral Note:", note);
      }});
    }};

    function sortTable(key) {{
      if (state.sortKey === key) {{
        state.sortAsc = !state.sortAsc;
      }} else {{
        state.sortKey = key;
        state.sortAsc = true;
      }}
      renderTable();
    }}

    // Event listeners
    document.getElementById('searchQ').addEventListener('input', e => {{
      state.search = e.target.value;
      renderTable();
    }});
    document.getElementById('selReferral').addEventListener('change', e => {{ refFilter = e.target.value; renderTable(); }});
    document.getElementById('selStatus').addEventListener('change', e => {{
      state.status = e.target.value;
      renderTable();
    }});
    document.getElementById('selCountry').addEventListener('change', e => {{
      state.country = e.target.value;
      renderTable();
    }});
    document.getElementById('selCity').addEventListener('change', e => {{
      state.city = e.target.value;
      renderTable();
    }});
    document.getElementById('selCompany').addEventListener('change', e => {{
      state.company = e.target.value;
      renderTable();
    }});
    document.getElementById('selVisa').addEventListener('change', e => {{
      state.visa = e.target.value;
      renderTable();
    }});
    document.getElementById('selExp').addEventListener('change', e => {{
      state.exp = e.target.value;
      renderTable();
    }});

    document.getElementById('btnReset').addEventListener('click', () => {{
      state = {{ search: '', status: 'all', country: '', city: '', company: '', visa: '', exp: '', sortKey: 'id', sortAsc: true }};
      document.getElementById('searchQ').value = '';
      document.getElementById('selStatus').value = 'all';
      document.getElementById('selCountry').value = '';
      document.getElementById('selCity').value = '';
      document.getElementById('selCompany').value = '';
      document.getElementById('selVisa').value = '';
      document.getElementById('selExp').value = '';
      renderTable();
    }});

    document.getElementById('btnCopyApplied').addEventListener('click', () => {{
      const list = [...appliedJobs].join(', ');
      if (!list) {{
        alert('No jobs marked as applied yet! Click "Mark Applied" on any row.');
        return;
      }}
      navigator.clipboard.writeText(list).then(() => {{
        alert(`Copied ${{appliedJobs.size}} applied job IDs to clipboard:\\n${{list}}`);
      }});
    }});

    document.getElementById('btnSyncTelegram').addEventListener('click', () => {{
      if (appliedJobs.size === 0) {{
        alert('No jobs marked as applied yet! Click "Mark Applied" on any row first.');
        return;
      }}
      const idList = [...appliedJobs].join(' ');
      const tgUrl = `https://t.me/jobsearch_chan23_bot?text=${{encodeURIComponent('/applied ' + idList)}}`;
      window.open(tgUrl, '_blank');
    }});

    document.getElementById('btnEditContact').addEventListener('click', () => {{
      const curName = localStorage.getItem('user_name') || '{user_name}';
      const curPhone = localStorage.getItem('user_phone') || '{user_phone}';
      const curEmail = localStorage.getItem('user_email') || '{user_email}';

      const n = prompt('Enter your Full Name for referral messages:', curName);
      if (n !== null && n.trim()) localStorage.setItem('user_name', n.trim());

      const p = prompt('Enter your Phone Number for referral messages:', curPhone);
      if (p !== null && p.trim()) localStorage.setItem('user_phone', p.trim());

      const e = prompt('Enter your Email Address for referral messages:', curEmail);
      if (e !== null && e.trim()) localStorage.setItem('user_email', e.trim());

      alert('✅ Contact details saved! Every "Referral Note" will now include your updated name, phone, and email.');
    }});

    renderTable();

    // Render Charts
    const compCounts = {{}};
    JOBS.forEach(j => compCounts[j.company] = (compCounts[j.company] || 0) + 1);
    const topComps = Object.entries(compCounts).sort((a,b) => b[1] - a[1]).slice(0, 10);

    window.Chart && new Chart(document.getElementById('chartCompany'), {{
      type: 'bar',
      data: {{
        labels: topComps.map(c => c[0]),
        datasets: [{{
          data: topComps.map(c => c[1]),
          backgroundColor: '#3b82f6',
          borderRadius: 4
        }}]
      }},
      options: {{
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{ x: {{ ticks: {{ stepSize: 1 }} }} }}
      }}
    }});

    const locCounts = {{ 'India': 0, 'UK': 0, 'Australia': 0 }};
    JOBS.forEach(j => {{ if (locCounts[j.country] !== undefined) locCounts[j.country]++; }});

    window.Chart && new Chart(document.getElementById('chartLocation'), {{
      type: 'doughnut',
      data: {{
        labels: Object.keys(locCounts),
        datasets: [{{
          data: Object.values(locCounts),
          backgroundColor: ['#10b981', '#3b82f6', '#f59e0b'],
          borderWidth: 0
        }}]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ position: 'bottom' }} }}
      }}
    }});

    const visaCounts = {{}};
    JOBS.forEach(j => visaCounts[j.visaCat] = (visaCounts[j.visaCat] || 0) + 1);

    window.Chart && new Chart(document.getElementById('chartVisa'), {{
      type: 'doughnut',
      data: {{
        labels: Object.keys(visaCounts),
        datasets: [{{
          data: Object.values(visaCounts),
          backgroundColor: ['#10b981', '#f59e0b', '#3b82f6', '#94a3b8'],
          borderWidth: 0
        }}]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ position: 'bottom' }} }}
      }}
    }});
  </script>
</body>
</html>
"""
    out_html = PROJECT_DIR / "index.html"
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generated standalone web dashboard with interactive application tracking at {out_html}")

if __name__ == "__main__":
    build_dashboard()
