"""Strip credential-shaped substrings before anything is logged or committed."""
import re

_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"ghp_[A-Za-z0-9]+"),
    re.compile(r"gho_[A-Za-z0-9]+"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]+"),
    re.compile(r"bot\d+:[A-Za-z0-9_-]+"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)\S+"),
    re.compile(r"(?i)(bot_token[\"']?\s*[:=]\s*[\"'])[^\"']+"),
)


def redact(text) -> str:
    out = str(text)
    for pat in _PATTERNS:
        out = pat.sub(lambda m: (m.group(1) + "<redacted>") if m.lastindex else "<redacted>", out)
    return out
