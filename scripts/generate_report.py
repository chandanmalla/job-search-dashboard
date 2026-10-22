"""
Job Search Report Generator
============================
Reads a JSON file of found jobs produced by the search agent,
generates an Excel workbook (4 sheets) + a self-contained HTML dashboard,
updates the de-duplication DB, and sends a Telegram notification.

Usage:
    python generate_report.py --jobs found_jobs.json
"""

import argparse
import json
import os
import sys
import subprocess
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap pip + third-party packages in the embedded Python environment
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
PY_EMBED  = SCRIPT_DIR / "python-embed"
PIP_BOOTSTRAP = PY_EMBED / "pip_bootstrap_done.flag"

def _ensure_packages():
    """Install openpyxl and xlsxwriter if not present (embedded Python)."""
    try:
        import openpyxl  # noqa: F401
        import xlsxwriter  # noqa: F401
        return
    except ImportError:
        pass

    print("[bootstrap] Installing required packages …", flush=True)
    get_pip = PY_EMBED / "get-pip.py"
    if not get_pip.exists():
        url = "https://bootstrap.pypa.io/get-pip.py"
        print(f"[bootstrap] Downloading get-pip from {url}", flush=True)
        urllib.request.urlretrieve(url, str(get_pip))

    subprocess.check_call([sys.executable, str(get_pip), "--no-warn-script-location"])
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "openpyxl", "xlsxwriter", "--no-warn-script-location"])
    PIP_BOOTSTRAP.touch()
    print("[bootstrap] Packages installed.", flush=True)


_ensure_packages()
import openpyxl  # noqa: E402
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402
from openpyxl.chart import BarChart, Reference  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_PATH = SCRIPT_DIR / "config.json"

def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)

# ---------------------------------------------------------------------------
# Tracked Jobs DB (de-duplication)
# ---------------------------------------------------------------------------

def load_db(path: str) -> dict:
    p = Path(path)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"seen_keys": [], "all_jobs": [], "applied": [], "skipped": [], "next_id": 1}


def save_db(path: str, db: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def job_key(job: dict) -> str:
    return f"{job.get('company','').lower()}|{job.get('job_title','').lower()}"


def assign_job_id(job: dict, db: dict) -> str:
    """Assign a short stable ID like J001 to a job if it doesn't have one yet."""
    if job.get("job_id"):
        return job["job_id"]
    next_id = db.get("next_id", 1)
    jid = f"J{next_id:03d}"
    job["job_id"] = jid
    db["next_id"] = next_id + 1
    return jid


def find_new_jobs(found: list, db: dict) -> list:
    seen    = set(db.get("seen_keys", []))
    applied = set(db.get("applied", []))
    skipped = set(db.get("skipped", []))
    new = []
    for j in found:
        # Strict exclusion of Amazon and Principal/Staff roles
        if "amazon" in j.get("company", "").lower() or "aws" in j.get("company", "").lower():
            continue
        if any(w in j.get("job_title", "").lower() for w in ["principal", "staff"]):
            continue

        k = job_key(j)
        if k not in seen:
            new.append(j)
    # Safety-net: exclude anything already actioned
    new = [j for j in new if j.get("job_id", "") not in applied
                           and j.get("job_id", "") not in skipped]
    return new


# ---------------------------------------------------------------------------
# Excel workbook builder
# ---------------------------------------------------------------------------

HEADER_FILL   = PatternFill("solid", fgColor="1F4E79")
ALT_FILL      = PatternFill("solid", fgColor="D6E4F0")
STRETCH_FILL  = PatternFill("solid", fgColor="FFF2CC")
GREEN_FILL    = PatternFill("solid", fgColor="E2EFDA")
WHITE_FILL    = PatternFill("solid", fgColor="FFFFFF")
HEADER_FONT   = Font(color="FFFFFF", bold=True, size=11)
TITLE_FONT    = Font(bold=True, size=14, color="1F4E79")
BOLD_FONT     = Font(bold=True)
THIN_BORDER   = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin")
)

COLS = [
    "Company", "Job Title", "Location", "Date Posted",
    "Experience Fit", "Technical Fit",
    "Visa Sponsorship", "Relocation",
    "Direct Application Link", "Source"
]

COL_WIDTHS = [22, 38, 24, 14, 18, 18, 24, 14, 50, 22]


def _write_header(ws, row=1):
    for ci, (col, w) in enumerate(zip(COLS, COL_WIDTHS), start=1):
        cell = ws.cell(row=row, column=ci, value=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.row_dimensions[row].height = 28


def _write_job_row(ws, row_idx: int, job: dict, is_alt: bool):
    fill = ALT_FILL if is_alt else WHITE_FILL
    if job.get("stretch"):
        fill = STRETCH_FILL

    values = [
        job.get("company", ""),
        job.get("job_title", ""),
        job.get("location", ""),
        job.get("date_posted", "Unverified"),
        job.get("experience_fit", ""),
        job.get("technical_fit", ""),
        job.get("visa_sponsorship", "Unknown"),
        job.get("relocation", "Unknown"),
        job.get("link", ""),
        job.get("source", ""),
    ]

    for ci, val in enumerate(values, start=1):
        cell = ws.cell(row=row_idx, column=ci, value=val)
        cell.fill = fill
        cell.border = THIN_BORDER
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        if ci == 9 and val.startswith("http"):  # hyperlink
            cell.hyperlink = val
            cell.font = Font(color="0563C1", underline="single")
        else:
            cell.font = Font(size=10)


def build_excel(new_jobs: list, all_jobs: list, run_ts: str, out_path: str):
    wb = openpyxl.Workbook()

    # ---- Sheet 1: Dashboard ------------------------------------------------
    ws1 = wb.active
    ws1.title = "Dashboard"

    ws1["A1"] = "🎯 Job Search Dashboard"
    ws1["A1"].font = Font(bold=True, size=18, color="1F4E79")
    ws1["A1"].alignment = Alignment(horizontal="left")
    ws1.merge_cells("A1:J1")

    ws1["A2"] = f"Last refreshed: {run_ts}  |  New this run: {len(new_jobs)}  |  Total tracked: {len(all_jobs)}"
    ws1["A2"].font = Font(italic=True, size=10, color="595959")
    ws1.merge_cells("A2:J2")

    # Top picks
    ws1["A4"] = "🏆 Top Picks This Run"
    ws1["A4"].font = Font(bold=True, size=13, color="1F4E79")

    picks = sorted(new_jobs, key=lambda j: (j.get("experience_fit","") == "Good fit", j.get("technical_fit","") == "Strong"), reverse=True)[:10]
    headers_p = ["#", "Company", "Job Title", "Location", "Visa Sponsorship", "Link", "Why It Fits"]
    pick_col_w = [4, 22, 36, 22, 24, 40, 50]
    for ci, (h, w) in enumerate(zip(headers_p, pick_col_w), start=1):
        cell = ws1.cell(row=5, column=ci, value=h)
        cell.font = HEADER_FONT; cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center"); cell.border = THIN_BORDER
        ws1.column_dimensions[get_column_letter(ci)].width = w

    for ri, job in enumerate(picks, start=6):
        row_fill = GREEN_FILL if (ri % 2 == 0) else WHITE_FILL
        row_vals = [
            ri - 5, job.get("company",""), job.get("job_title",""),
            job.get("location",""), job.get("visa_sponsorship","Unknown"),
            job.get("link",""), job.get("why_fits","")
        ]
        for ci, val in enumerate(row_vals, start=1):
            cell = ws1.cell(row=ri, column=ci, value=val)
            cell.fill = row_fill; cell.border = THIN_BORDER
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if ci == 6 and str(val).startswith("http"):
                cell.hyperlink = val
                cell.font = Font(color="0563C1", underline="single")
            else:
                cell.font = Font(size=10)

    # Summary stats table (for charting)
    stat_start_row = len(picks) + 8
    ws1.cell(row=stat_start_row, column=1, value="Region").font = BOLD_FONT
    ws1.cell(row=stat_start_row, column=2, value="Count").font = BOLD_FONT

    regions = {}
    for j in all_jobs:
        loc = j.get("location", "Unknown")
        r = "India" if any(x in loc for x in ["India", "Bangalore", "Delhi", "Hyderabad", "Gurgaon", "Mumbai", "Remote IN"]) \
            else "UK" if "UK" in loc or "London" in loc or "United Kingdom" in loc \
            else "Australia" if "Australia" in loc or "Sydney" in loc or "Melbourne" in loc \
            else "Remote / Other"
        regions[r] = regions.get(r, 0) + 1

    for ri2, (reg, cnt) in enumerate(sorted(regions.items()), start=stat_start_row + 1):
        ws1.cell(row=ri2, column=1, value=reg)
        ws1.cell(row=ri2, column=2, value=cnt)

    # Bar chart: Roles by region
    if regions:
        chart = BarChart()
        chart.type = "col"; chart.title = "Roles by Region"
        chart.style = 10; chart.y_axis.title = "Count"; chart.x_axis.title = "Region"
        chart.width = 18; chart.height = 10
        data_ref = Reference(ws1, min_col=2, min_row=stat_start_row,
                             max_row=stat_start_row + len(regions))
        cats_ref = Reference(ws1, min_col=1, min_row=stat_start_row + 1,
                             max_row=stat_start_row + len(regions))
        chart.add_data(data_ref, titles_from_data=True)
        chart.set_categories(cats_ref)
        ws1.add_chart(chart, f"D{stat_start_row}")

    # ---- Sheet 2: New Jobs -------------------------------------------------
    ws2 = wb.create_sheet("New Jobs")
    _write_header(ws2)
    for ri, job in enumerate(new_jobs, start=2):
        _write_job_row(ws2, ri, job, ri % 2 == 0)
    ws2.freeze_panes = "A2"
    ws2.auto_filter.ref = f"A1:{get_column_letter(len(COLS))}1"

    # ---- Sheet 3: All Tracked ----------------------------------------------
    ws3 = wb.create_sheet("All Tracked")
    _write_header(ws3)
    for ri, job in enumerate(all_jobs, start=2):
        _write_job_row(ws3, ri, job, ri % 2 == 0)
    ws3.freeze_panes = "A2"
    ws3.auto_filter.ref = f"A1:{get_column_letter(len(COLS))}1"

    # ---- Sheet 4: Summary --------------------------------------------------
    ws4 = wb.create_sheet("Summary")
    ws4["A1"] = "Summary Report"
    ws4["A1"].font = TITLE_FONT
    ws4.merge_cells("A1:D1")

    ws4["A3"] = "Run Timestamp"; ws4["B3"] = run_ts
    ws4["A4"] = "New Jobs This Run"; ws4["B4"] = len(new_jobs)
    ws4["A5"] = "Total Jobs Tracked"; ws4["B5"] = len(all_jobs)

    ws4["A7"] = "Region"; ws4["B7"] = "Count"
    ws4["A7"].font = BOLD_FONT; ws4["B7"].font = BOLD_FONT
    for ri, (reg, cnt) in enumerate(sorted(regions.items()), start=8):
        ws4.cell(row=ri, column=1, value=reg)
        ws4.cell(row=ri, column=2, value=cnt)

    comp_start = 8 + len(regions) + 2
    ws4.cell(row=comp_start - 1, column=1, value="Company").font = BOLD_FONT
    ws4.cell(row=comp_start - 1, column=2, value="Count").font = BOLD_FONT
    comps = {}
    for j in all_jobs:
        comps[j.get("company", "Unknown")] = comps.get(j.get("company", "Unknown"), 0) + 1
    for ri, (comp, cnt) in enumerate(sorted(comps.items(), key=lambda x: -x[1]), start=comp_start):
        ws4.cell(row=ri, column=1, value=comp)
        ws4.cell(row=ri, column=2, value=cnt)

    ws4.column_dimensions["A"].width = 32
    ws4.column_dimensions["B"].width = 16

    sites_row = comp_start + len(comps) + 3
    ws4.cell(row=sites_row, column=1, value="Sites Checked / Notes").font = BOLD_FONT
    notes = [
        "Greenhouse ATS feeds", "Lever ATS feeds", "Ashby ATS feeds",
        "LinkedIn job search", "Naukri.com", "Wellfound",
        "Company career pages (selected)", "Gov.uk visa sponsor register (UK roles)"
    ]
    for ri, note in enumerate(notes, start=sites_row + 1):
        ws4.cell(row=ri, column=1, value=note)

    wb.save(out_path)
    print(f"[excel] Saved: {out_path}", flush=True)

# ---------------------------------------------------------------------------
# HTML Dashboard builder
# ---------------------------------------------------------------------------

def build_html(new_jobs: list, all_jobs: list, run_ts: str, out_path: str):
    def esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    regions = {}
    companies = {}
    for j in all_jobs:
        loc = j.get("location", "Unknown")
        r = "India" if any(x in loc for x in ["India","Bangalore","Delhi","Hyderabad","Gurgaon","Mumbai","Remote IN"]) \
            else "UK" if ("UK" in loc or "London" in loc or "United Kingdom" in loc) \
            else "Australia" if ("Australia" in loc or "Sydney" in loc or "Melbourne" in loc) \
            else "Remote / Other"
        regions[r] = regions.get(r, 0) + 1
        c = j.get("company", "Unknown")
        companies[c] = companies.get(c, 0) + 1

    region_labels = list(regions.keys())
    region_counts = [regions[k] for k in region_labels]
    top_companies = sorted(companies.items(), key=lambda x: -x[1])[:15]
    comp_labels = [x[0] for x in top_companies]
    comp_counts = [x[1] for x in top_companies]

    def table_rows(jobs):
        rows = []
        for j in jobs:
            link = j.get("link", "")
            link_html = f'<a href="{esc(link)}" target="_blank">Apply ↗</a>' if link.startswith("http") else esc(link)
            stretch = "stretch-row" if j.get("stretch") else ""
            visa = esc(j.get("visa_sponsorship", "Unknown"))
            visa_cls = "badge-green" if "Confirmed" in visa else "badge-yellow" if "Plausible" in visa else "badge-grey"
            rows.append(f"""
            <tr class="{stretch}">
              <td>{esc(j.get('company',''))}</td>
              <td>{esc(j.get('job_title',''))}</td>
              <td>{esc(j.get('location',''))}</td>
              <td>{esc(j.get('date_posted',''))}</td>
              <td>{esc(j.get('experience_fit',''))}</td>
              <td>{esc(j.get('technical_fit',''))}</td>
              <td><span class="badge {visa_cls}">{visa}</span></td>
              <td>{esc(j.get('relocation','Unknown'))}</td>
              <td>{link_html}</td>
              <td>{esc(j.get('source',''))}</td>
            </tr>""")
        return "".join(rows)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Job Search Dashboard — {esc(run_ts)}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --blue: #1F4E79; --lightblue: #D6E4F0; --green: #70AD47;
    --yellow: #FFC000; --grey: #7F7F7F; --bg: #F5F7FA;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', sans-serif; background: var(--bg); color: #222; }}
  header {{ background: var(--blue); color: #fff; padding: 18px 32px; }}
  header h1 {{ font-size: 1.6rem; }}
  header p {{ font-size: 0.85rem; opacity: .8; margin-top: 4px; }}
  .stats {{ display: flex; gap: 16px; padding: 20px 32px; flex-wrap: wrap; }}
  .stat-card {{ background: #fff; border-radius: 10px; padding: 18px 28px;
                box-shadow: 0 2px 8px rgba(0,0,0,.08); min-width: 160px; }}
  .stat-card .num {{ font-size: 2rem; font-weight: 700; color: var(--blue); }}
  .stat-card .lbl {{ font-size: 0.82rem; color: var(--grey); margin-top: 4px; }}
  .charts {{ display: flex; gap: 24px; padding: 0 32px 24px; flex-wrap: wrap; }}
  .chart-box {{ background: #fff; border-radius: 10px; padding: 20px;
                box-shadow: 0 2px 8px rgba(0,0,0,.08); flex: 1; min-width: 320px; max-width: 600px; }}
  .chart-box h2 {{ font-size: 1rem; color: var(--blue); margin-bottom: 12px; }}
  .section {{ padding: 0 32px 32px; }}
  .section h2 {{ font-size: 1.1rem; color: var(--blue); margin-bottom: 12px;
                 border-left: 4px solid var(--blue); padding-left: 10px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff;
           border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,.08); font-size: 0.82rem; }}
  th {{ background: var(--blue); color: #fff; padding: 10px 12px; text-align: left; white-space: nowrap; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #E8EEF4; vertical-align: top; }}
  tr:nth-child(even) td {{ background: var(--lightblue); }}
  tr.stretch-row td {{ background: #FFF2CC !important; }}
  a {{ color: var(--blue); }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.75rem; font-weight: 600; }}
  .badge-green {{ background: #E2EFDA; color: #375623; }}
  .badge-yellow {{ background: #FFF2CC; color: #7F6000; }}
  .badge-grey {{ background: #EDEDED; color: #595959; }}
  .tabs {{ display: flex; gap: 8px; margin-bottom: 12px; }}
  .tab-btn {{ padding: 8px 20px; border: 2px solid var(--blue); border-radius: 6px;
              background: #fff; color: var(--blue); cursor: pointer; font-weight: 600; }}
  .tab-btn.active {{ background: var(--blue); color: #fff; }}
  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}
</style>
</head>
<body>
<header>
  <h1>🎯 Job Search Dashboard</h1>
  <p>Last refreshed: {esc(run_ts)} &nbsp;|&nbsp; New this run: {len(new_jobs)} &nbsp;|&nbsp; Total tracked: {len(all_jobs)}</p>
</header>

<div class="stats">
  <div class="stat-card"><div class="num">{len(new_jobs)}</div><div class="lbl">New Jobs This Run</div></div>
  <div class="stat-card"><div class="num">{len(all_jobs)}</div><div class="lbl">Total Tracked</div></div>
  <div class="stat-card"><div class="num">{sum(1 for j in all_jobs if 'Confirmed' in j.get('visa_sponsorship',''))}</div><div class="lbl">Visa Confirmed</div></div>
  <div class="stat-card"><div class="num">{len(set(j.get('company','') for j in all_jobs))}</div><div class="lbl">Companies</div></div>
</div>

<div class="charts">
  <div class="chart-box">
    <h2>Roles by Region</h2>
    <canvas id="regionChart" height="220"></canvas>
  </div>
  <div class="chart-box">
    <h2>Top Companies</h2>
    <canvas id="companyChart" height="220"></canvas>
  </div>
</div>

<div class="section">
  <div class="tabs">
    <button class="tab-btn active" onclick="showTab('new')">New Jobs ({len(new_jobs)})</button>
    <button class="tab-btn" onclick="showTab('all')">All Tracked ({len(all_jobs)})</button>
  </div>
  <div id="new" class="tab-content active">
    <table>
      <thead><tr><th>Company</th><th>Title</th><th>Location</th><th>Date</th><th>Exp Fit</th><th>Tech Fit</th><th>Visa</th><th>Relocation</th><th>Link</th><th>Source</th></tr></thead>
      <tbody>{table_rows(new_jobs)}</tbody>
    </table>
  </div>
  <div id="all" class="tab-content">
    <table>
      <thead><tr><th>Company</th><th>Title</th><th>Location</th><th>Date</th><th>Exp Fit</th><th>Tech Fit</th><th>Visa</th><th>Relocation</th><th>Link</th><th>Source</th></tr></thead>
      <tbody>{table_rows(all_jobs)}</tbody>
    </table>
  </div>
</div>

<script>
function showTab(id) {{
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  event.target.classList.add('active');
}}

new Chart(document.getElementById('regionChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(region_labels)},
    datasets: [{{ label: 'Roles', data: {json.dumps(region_counts)},
      backgroundColor: ['#1F4E79','#2E75B6','#70AD47','#FFC000'], borderRadius: 6 }}]
  }},
  options: {{ plugins: {{ legend: {{ display: false }} }}, responsive: true }}
}});

new Chart(document.getElementById('companyChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(comp_labels)},
    datasets: [{{ label: 'Roles', data: {json.dumps(comp_counts)},
      backgroundColor: '#2E75B6', borderRadius: 6 }}]
  }},
  options: {{
    indexAxis: 'y', plugins: {{ legend: {{ display: false }} }},
    responsive: true, scales: {{ x: {{ beginAtZero: true, ticks: {{ stepSize: 1 }} }} }}
  }}
}});
</script>
</body>
</html>"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[html] Saved: {out_path}", flush=True)

# ---------------------------------------------------------------------------
# Telegram notifier
# ---------------------------------------------------------------------------

def _tg_post(token: str, payload: dict):
    url  = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(payload).encode()
    try:
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"[telegram] Failed: {e}", flush=True)
        return {"ok": False}


def esc_html(text: str) -> str:
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_job_digest_entry(job: dict) -> str:
    jid = job.get("job_id", "?")
    comp = esc_html(job.get("company", ""))
    title = esc_html(job.get("job_title", ""))
    posted = esc_html(job.get("date_posted", ""))
    link = job.get("link", "")
    apply_html = f'<a href="{link}">Apply Direct ↗</a>' if link.startswith("http") else '<i>No link</i>'
    posted_tag = f"  ⏱ <i>{posted}</i>\n" if posted and "unverified" not in posted.lower() else ""

    return (
        f"• <b>{jid}</b> | <b>{comp}</b>\n"
        f"  📌 {title}\n"
        f"{posted_tag}"
        f"  🔗 {apply_html}  •  <code>/applied {jid}</code>\n\n"
    )


def send_telegram(token: str, chat_targets, new_jobs: list, excel_path: str, html_path: str, run_ts: str):
    """Send all new jobs consolidated into digest messages rather than individual cards."""
    if isinstance(chat_targets, (str, int)):
        chat_ids = [str(chat_targets)]
    elif isinstance(chat_targets, list):
        chat_ids = [str(cid) for cid in chat_targets]
    else:
        chat_ids = []

    n = len(new_jobs)
    import time as _time
    uprofile = load_config().get("user_profile", {})

    for chat_id in chat_ids:
        if n == 0:
            _tg_post(token, {
                "chat_id": chat_id,
                "text": (
                    f"🔍 <b>Job Search Update</b> ({esc_html(run_ts)})\n\n"
                    "No new roles found this run. Total tracked stays the same.\n"
                    "Next check in ~4 hours."
                ),
                "parse_mode": "HTML",
            })
            print(f"[telegram] 'No new jobs' message sent to {chat_id}.", flush=True)
            continue

        header = (
            f"🎯 <b>Job Search Digest — {n} new role{'s' if n != 1 else ''} found!</b>\n"
            f"🕐 {esc_html(run_ts)}\n"
            f"📗 Excel: <code>{esc_html(excel_path)}</code>\n\n"
        )
        footer = "<i>Mark with <code>/applied &lt;ID&gt;</code> or <code>/skip &lt;ID&gt;</code></i>"

        messages = []
        current_msg = header
        for j in new_jobs:
            entry = format_job_digest_entry(j)
            if len(current_msg) + len(entry) + len(footer) > 3800:
                messages.append(current_msg + footer)
                current_msg = "🎯 <b>Job Search Digest (cont.)</b>\n\n" + entry
            else:
                current_msg += entry
        if current_msg:
            messages.append(current_msg + footer)

        total_parts = len(messages)
        for idx, m in enumerate(messages, start=1):
            part_label = f" [Part {idx}/{total_parts}]" if total_parts > 1 else ""
            if total_parts > 1:
                m = m.replace("🎯 <b>Job Search Digest", f"🎯 <b>Job Search Digest{part_label}")

            _tg_post(token, {
                "chat_id": chat_id,
                "text": m,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true"
            })
            _time.sleep(0.5)

        print(f"[telegram] Sent consolidated digest ({len(messages)} messages) to {chat_id}.", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Job Search Report Generator")
    parser.add_argument("--jobs", required=True, help="Path to found_jobs.json produced by the agent")
    args = parser.parse_args()

    cfg = load_config()
    output_dir = Path(cfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(args.jobs, encoding="utf-8") as f:
        found_jobs = json.load(f)

    db       = load_db(cfg["tracked_jobs_db"])
    new_jobs = find_new_jobs(found_jobs, db)

    chat_targets = cfg.get("telegram", {}).get("chat_ids") or cfg.get("telegram", {}).get("chat_id")

    if not new_jobs:
        print("[main] No new jobs found. Sending Telegram notification.", flush=True)
        run_ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
        send_telegram(cfg["telegram"]["bot_token"], chat_targets,
                      [], "", "", run_ts)
        return

    # Assign stable job IDs before saving
    for j in new_jobs:
        assign_job_id(j, db)

    # Update DB
    for j in new_jobs:
        db["seen_keys"].append(job_key(j))
        db["all_jobs"].append(j)
    save_db(cfg["tracked_jobs_db"], db)

    all_jobs = db["all_jobs"]
    run_ts   = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    stamp    = datetime.now().strftime("%Y%m%d_%H%M")

    excel_path = str(output_dir / f"job_report_{stamp}.xlsx")
    html_path  = str(output_dir / f"job_dashboard_{stamp}.html")

    build_excel(new_jobs, all_jobs, run_ts, excel_path)
    build_html(new_jobs, all_jobs, run_ts, html_path)

    # Auto-open HTML
    if cfg.get("auto_open_html"):
        try:
            os.startfile(html_path)
        except Exception:
            pass

    send_telegram(cfg["telegram"]["bot_token"], chat_targets,
                  new_jobs, excel_path, html_path, run_ts)

    print(f"[main] Done. {len(new_jobs)} new jobs. Reports at {output_dir}", flush=True)


if __name__ == "__main__":
    main()
