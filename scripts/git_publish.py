"""Commit an explicit file list and push, retrying by replaying the mutation.

Resets to origin/<branch> only when allow_reset=True (CI publish). Never stages
config, env, token, or key files. Mutation callbacks must be idempotent: each
attempt starts from origin.
"""
import subprocess
from pathlib import Path

from redact import redact

FORBIDDEN_NAMES = {
    "config.json",
    ".env",
    ".env.local",
    "secrets.json",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
}


class PublishRefused(RuntimeError):
    pass


class GitPublisher:
    def __init__(self, repo: Path, *, git="git", branch="main", remote="origin",
                 allow_reset=False, name="job-search-dashboard",
                 email="41898282+github-actions[bot]@users.noreply.github.com"):
        self.repo = Path(repo)
        self.git = git
        self.branch = branch
        self.remote = remote
        self.allow_reset = allow_reset
        self.name = name
        self.email = email

    def run(self, args, check=True):
        result = subprocess.run(
            [self.git, *args],
            cwd=self.repo,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            detail = redact((result.stderr or result.stdout or "").strip())
            raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
        return result

    def _identity(self):
        self.run(["config", "user.name", self.name])
        self.run(["config", "user.email", self.email])

    def _rel(self, path) -> str:
        candidate = Path(path)
        if candidate.is_absolute():
            candidate = candidate.relative_to(self.repo)
        if ".." in candidate.parts:
            raise PublishRefused(f"refusing path outside the repo: {candidate}")
        self._reject_name(candidate)
        return candidate.as_posix()

    def _reject_name(self, path: Path):
        name = path.name.lower()
        if name in FORBIDDEN_NAMES or name.endswith(".pem") or name.endswith(".env") or "token" in name:
            raise PublishRefused(f"refusing to commit {path.as_posix()}")

    def reset_to_origin(self):
        if not self.allow_reset:
            raise PublishRefused("refusing to reset the worktree without allow_reset")
        self.run(["fetch", self.remote, self.branch])
        self.run(["checkout", self.branch])
        self.run(["reset", "--hard", f"{self.remote}/{self.branch}"])

    def _staged_names(self):
        result = self.run(["diff", "--cached", "--name-only"])
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def sync_publish(self, rel_paths, message: str, mutate, retries: int = 3) -> dict:
        """mutate() rewrites files from the current origin snapshot. It must be idempotent."""
        self._identity()
        paths = [self._rel(path) for path in rel_paths]
        last_error = ""
        for attempt in range(1, retries + 1):
            self.reset_to_origin()
            mutate()
            for path in paths:
                self._reject_name(Path(path))
            existing = [path for path in paths if (self.repo / path).exists() or (self.repo / path).is_dir()]
            if not existing:
                return {"ok": True, "pushed": False, "attempts": attempt, "detail": "nothing to publish"}
            self.run(["add", "--", *existing])
            staged = self._staged_names()
            for name in staged:
                self._reject_name(Path(name))
            if not staged:
                return {"ok": True, "pushed": False, "attempts": attempt, "detail": "clean"}
            self.run(["commit", "-m", message])
            push = self.run(["push", self.remote, self.branch], check=False)
            if push.returncode == 0:
                return {"ok": True, "pushed": True, "attempts": attempt, "detail": "pushed"}
            last_error = redact((push.stderr or push.stdout or "").strip())
        self.reset_to_origin()
        return {"ok": False, "pushed": False, "attempts": retries, "detail": last_error}
