"""Git-Sicherheitsnetz: Es wird ausschliesslich innerhalb der in
agent-interface.json -> allowed_write_paths gelegenen Pfade 'git add'
aufgerufen (kein 'git add -A'/'git add .'). Dadurch bleiben bestehende,
nicht vom Agenten verursachte Aenderungen (z.B. an docs/index.html)
unangetastet -- sie werden nie gestaged und nie committet.

Commit/Push erfolgen erst, nachdem tools/validate_site.py Exit-Code 0
geliefert hat UND der gestagte Diff ausschliesslich erlaubte Pfade enthaelt.
"""

import subprocess
from pathlib import Path
from typing import List, Tuple

from . import config


class GitError(RuntimeError):
    pass


def _run(args: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args,
        cwd=str(config.WEBSITE_ROOT),
        capture_output=True,
        text=True,
    )


def stage_allowed_paths(allowed_write_paths: List[str]) -> List[str]:
    """Fuehrt 'git add <pfad>' fuer jeden erlaubten Pfad einzeln aus (Datei
    oder Verzeichnis-Praefix). Gibt die dabei uebergebenen Pfade zurueck."""
    staged_targets = []
    for rel_path in allowed_write_paths:
        abs_path = config.WEBSITE_ROOT / rel_path
        if not abs_path.exists():
            continue
        result = _run(["add", "--", rel_path])
        if result.returncode != 0:
            raise GitError(f"git add fehlgeschlagen fuer {rel_path}: {result.stderr.strip()}")
        staged_targets.append(rel_path)
    return staged_targets


def staged_paths() -> List[str]:
    result = _run(["diff", "--cached", "--name-only"])
    if result.returncode != 0:
        raise GitError(f"git diff --cached fehlgeschlagen: {result.stderr.strip()}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _path_is_allowed(path: str, allowed_write_paths: List[str]) -> bool:
    for allowed in allowed_write_paths:
        if allowed.endswith("/"):
            if path.startswith(allowed):
                return True
        elif path == allowed:
            return True
    return False


def verify_staged_diff(allowed_write_paths: List[str], protected_paths: List[str]) -> Tuple[bool, List[str]]:
    """Prueft den gestagten Diff: JEDER Pfad muss innerhalb von
    allowed_write_paths liegen, KEINER darf ein protected_paths-Eintrag
    sein. Gibt (ok, violations) zurueck."""
    violations = []
    for path in staged_paths():
        is_protected = any(path == p or (p.endswith("/") and path.startswith(p)) for p in protected_paths)
        is_allowed = _path_is_allowed(path, allowed_write_paths)
        if is_protected or not is_allowed:
            violations.append(path)
    return (len(violations) == 0, violations)


def unstage_all():
    _run(["reset", "HEAD", "--"])


def commit(message: str) -> str:
    result = _run(["commit", "-m", message])
    if result.returncode != 0:
        raise GitError(f"git commit fehlgeschlagen: {result.stderr.strip()}\n{result.stdout.strip()}")
    rev = _run(["rev-parse", "HEAD"])
    return rev.stdout.strip()


def push() -> str:
    result = _run(["push"])
    if result.returncode != 0:
        raise GitError(f"git push fehlgeschlagen: {result.stderr.strip()}")
    return result.stdout.strip() + result.stderr.strip()


def current_branch() -> str:
    result = _run(["rev-parse", "--abbrev-ref", "HEAD"])
    return result.stdout.strip()
