"""
Job Search Agent Orchestrator
==============================
This script is called by the scheduled automation. It drives the search agent,
collects results into a structured JSON file, then calls generate_report.py.

The search logic is handled by the Antigravity agent via the sidecar prompt.
This script is a thin wrapper: it prepares a found_jobs.json from stdin or
a temp file, then invokes generate_report.py.

Called with:
    python run_search.py --input found_jobs.json
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PY = str(SCRIPT_DIR / "python-embed" / "python.exe")
REPORT_SCRIPT = str(SCRIPT_DIR / "generate_report.py")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to found_jobs.json")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[run_search] Input file not found: {input_path}", flush=True)
        sys.exit(1)

    # Validate JSON
    with open(input_path, encoding="utf-8") as f:
        jobs = json.load(f)

    print(f"[run_search] Loaded {len(jobs)} jobs from {input_path}", flush=True)

    result = subprocess.run(
        [PY, REPORT_SCRIPT, "--jobs", str(input_path)],
        capture_output=False
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
