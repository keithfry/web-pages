"""Write the HTML digest to the repo and commit + push it."""

import subprocess
from datetime import datetime
from pathlib import Path

from config import REPO_ROOT, OUTPUT_DIR, GIT_USER_NAME, GIT_USER_EMAIL


def save_html(html: str, date: datetime) -> Path:
    """Write HTML to techradar/AI/ai-radar-YYYY-MM-DD.html and return the path."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"ai-radar-{date.strftime('%Y-%m-%d')}.html"
    out_path = OUTPUT_DIR / filename
    out_path.write_text(html, encoding="utf-8")
    return out_path


def _run(
    args: list[str],
    check: bool = True,
    log=print,
) -> subprocess.CompletedProcess:
    result = subprocess.run(args, capture_output=True, text=True, cwd=REPO_ROOT)
    if result.stdout.strip():
        log(f"  [git] {result.stdout.strip()}")
    if result.stderr.strip():
        log(f"  [git] {result.stderr.strip()}")
    if check and result.returncode != 0:
        raise RuntimeError(f"git command failed: {' '.join(args)}\n{result.stderr}")
    return result


def commit_and_push(out_path: Path, date: datetime, log=print) -> None:
    """git pull --rebase, add, commit, push."""
    rel_path = out_path.relative_to(REPO_ROOT)
    commit_msg = f"Add AI radar for {date.strftime('%Y-%m-%d')}"

    # Remove stale lock file if present
    lock = REPO_ROOT / ".git" / "index.lock"
    if lock.exists():
        lock.unlink()
        log("  removed stale .git/index.lock")

    _run(["git", "-C", str(REPO_ROOT), "pull", "--rebase", "--autostash"], log=log)
    _run(["git", "-C", str(REPO_ROOT), "add", str(rel_path)], log=log)

    result = _run(
        [
            "git", "-C", str(REPO_ROOT),
            "-c", f"user.name={GIT_USER_NAME}",
            "-c", f"user.email={GIT_USER_EMAIL}",
            "commit", "-m", commit_msg,
        ],
        check=False,
        log=log,
    )
    if result.returncode != 0:
        if "nothing to commit" in result.stdout + result.stderr:
            log("  nothing to commit, skipping push")
            return
        raise RuntimeError(f"git commit failed:\n{result.stderr}")

    _run(["git", "-C", str(REPO_ROOT), "push"], log=log)
    log(f"  pushed: {commit_msg}")
