"""Optional checkout of a private canonical-state repo.

Nothing is created here. Without STATE_REPO and STATE_REPO_TOKEN this prints
private_state=absent and leaves the public tree alone. The token is never printed.
"""
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import REPO_ROOT

DEST = REPO_ROOT / "state" / "private"
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


def prepare() -> int:
    repo = (os.environ.get("STATE_REPO") or "").strip()
    token = os.environ.get("STATE_REPO_TOKEN") or ""
    if not repo and not token:
        print("private_state=absent")
        return 0
    if not repo or not token or not _REPO.fullmatch(repo):
        print("private_state=invalid")
        return 2
    DEST.parent.mkdir(parents=True, exist_ok=True)
    if DEST.exists() and any(DEST.iterdir()):
        print("private_state=present")
        return 0
    ask_dir = Path(tempfile.mkdtemp(prefix="state-ask-"))
    ask = ask_dir / "askpass"
    ask.write_text("#!/bin/sh\nprintf '%s\\n' \"$STATE_REPO_TOKEN\"\n", encoding="utf-8")
    ask.chmod(stat.S_IRUSR | stat.S_IXUSR)
    env = dict(os.environ)
    env["GIT_ASKPASS"] = str(ask)
    env["GIT_TERMINAL_PROMPT"] = "0"
    result = subprocess.run(
        ["git", "clone", "--depth", "1", f"https://github.com/{repo}.git", str(DEST)],
        env=env,
        capture_output=True,
        text=True,
    )
    ask.unlink(missing_ok=True)
    ask_dir.rmdir()
    if result.returncode != 0:
        print("private_state=clone_failed")
        return 2
    print("private_state=ready")
    return 0


if __name__ == "__main__":
    sys.exit(prepare())
