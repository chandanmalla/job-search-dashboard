"""File-existence checks for the hosted pipeline. Does not execute job-tracker code."""
import ast
import sys
from pathlib import Path

APPLIED_FILES = (
    "tracked_jobs.json",
    "applied_updates.json",
    "skipped_updates.json",
    "referral_updates.json",
)
CRAWL_FILES = APPLIED_FILES + (
    "cron_state.json",
)
TELEGRAM_FILES = ("tg_offset.json",)
KNOWN_PIP = {
    "openpyxl", "xlsxwriter", "et_xmlfile", "requests", "urllib3", "certifi",
    "charset_normalizer", "idna", "bs4", "jobspy", "pandas", "numpy", "lxml",
    "dateutil", "pytz", "tzdata", "PIL", "yaml", "dotenv",
}


def required_names(mode: str, *, telegram_sync: bool = False) -> tuple:
    if mode == "preflight":
        names = list(CRAWL_FILES)
    elif mode == "crawl":
        names = list(CRAWL_FILES)
    elif mode == "applied-sync":
        names = list(APPLIED_FILES)
    else:
        raise ValueError(f"unknown mode {mode}")
    if telegram_sync:
        names.extend(TELEGRAM_FILES)
    return tuple(names)


def missing_files(jt: Path, names) -> list:
    jt = Path(jt)
    return [name for name in names if not (jt / name).is_file()]


def unresolved_local_imports(py_path: Path, search_dirs) -> list:
    """Non-stdlib imports that are neither a known pip package nor a local module file.

    The source is parsed, not executed, and is not returned.
    """
    try:
        tree = ast.parse(Path(py_path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        return [f"{Path(py_path).name}: could not parse ({exc.__class__.__name__})"]
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.append(node.module.split(".")[0])
    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    missing = []
    for module in sorted(set(modules)):
        if module in stdlib or module in KNOWN_PIP:
            continue
        if any((Path(directory) / f"{module}.py").is_file() for directory in search_dirs):
            continue
        missing.append(f"{Path(py_path).name} imports {module}")
    return missing


def preflight_report(jt: Path, mode: str, *, telegram_sync: bool = False, scripts_dir: Path | None = None) -> dict:
    jt = Path(jt)
    names = required_names(mode, telegram_sync=telegram_sync)
    absent = missing_files(jt, names)
    search = [jt]
    if scripts_dir is not None:
        search.append(Path(scripts_dir))
    unresolved = []
    for name in names:
        if name.endswith(".py") and (jt / name).is_file():
            unresolved.extend(unresolved_local_imports(jt / name, search))
    return {
        "mode": mode,
        "jt": str(jt),
        "missing_files": absent,
        "unresolved_imports": unresolved,
        "ready": not absent and not unresolved,
    }
