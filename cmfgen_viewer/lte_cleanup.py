"""Recoverable cleanup of known top-level LTE scratch and population files."""

from fnmatch import fnmatchcase
import os
from pathlib import Path
import stat

from .model_staging import MODEL_CLEANUP_FILES, MODEL_CLEANUP_PATTERNS, _human_size
from .workflow_permissions import make_readable, mkdir_readable


class LteCleanupError(ValueError):
    """Cleanup cannot safely use the reviewed candidate list."""


# Keep controls, scientific handoff products, and retained run diagnostics.
RETAINED_FILES = {
    "VADAT", "MODEL_SPEC", "GRID_PARAMS", "HYDRO_PARAMS", "GAMMAS", "MODEL", "RVTJ",
    "ROSSELAND_LTE_TAB", "RVSIG_COL", "RVSIG_COL_NEW", "RVSIG_COL_OLD",
    "OUTLTE", "WIND_HYD", "OUT_PARAMS", "ML_COUNTER", "TIMING", "ltebat.log",
    "ltebat.sh", "clean.sh", "atomic_links.json",
}
FILE_SIGNATURE_KEYS = ("size", "modified_ns", "changed_ns", "device", "inode")
SIGNATURE_KEYS = ("name", *FILE_SIGNATURE_KEYS, "kind", "target")


def _reason(name: str) -> str | None:
    if name in RETAINED_FILES or name.endswith("_IN"):
        return None
    if name.endswith("OUT"):
        return "Ion/continuum output"
    if name.startswith("POP"):
        return "Population workspace"
    if name.startswith("fort.") and name[5:].isdigit():
        return "Fortran scratch unit"
    if name in MODEL_CLEANUP_FILES:
        return MODEL_CLEANUP_FILES[name]
    for pattern, reason in MODEL_CLEANUP_PATTERNS:
        if fnmatchcase(name, pattern):
            return reason
    return None


def inspect_lte_cleanup(lte_dir: Path) -> dict:
    entries = []
    if lte_dir.is_dir() and not lte_dir.is_symlink():
        for child in lte_dir.iterdir():
            try:
                info = child.lstat()
                is_link = stat.S_ISLNK(info.st_mode)
                target = os.readlink(child) if is_link else ""
            except FileNotFoundError:
                continue
            # Remove the directory entry for a link, never inspect its target.
            # Regular shared inputs and real subdirectories remain excluded.
            if is_link:
                reason = "Top-level symlink (clean.sh rmlinks)"
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                reason = _reason(child.name)
            else:
                continue
            if reason is None:
                continue
            entries.append({
                "name": child.name, "reason": reason, "size": info.st_size,
                "kind": "Symlink" if is_link else "File", "target": target,
                "human_size": _human_size(info.st_size), "modified_ns": info.st_mtime_ns,
                "changed_ns": info.st_ctime_ns, "device": info.st_dev, "inode": info.st_ino,
            })
    entries.sort(key=lambda item: item["name"].lower())
    total_size = sum(item["size"] for item in entries)
    return {"entries": entries, "entry_count": len(entries), "total_size": total_size,
            "human_size": _human_size(total_size)}


def validate_lte_cleanup(lte_dir: Path, expected_entries) -> dict:
    plan = inspect_lte_cleanup(lte_dir)
    if expected_entries is not None:
        before = {item["name"]: tuple(item[key] for key in SIGNATURE_KEYS) for item in expected_entries}
        now = {item["name"]: tuple(item[key] for key in SIGNATURE_KEYS) for item in plan["entries"]}
        if before != now:
            raise LteCleanupError("LTE temporary files changed since review; preview again.")
    return plan


def archive_lte_temporaries(lte_dir: Path, archive_dir: Path, *, expected_entries=None) -> dict:
    """Move reviewed files without overwriting; callers hold the model write guard."""
    if lte_dir.is_symlink() or not lte_dir.is_dir():
        raise LteCleanupError("LTE workspace must be a real directory.")
    plan = validate_lte_cleanup(lte_dir, expected_entries)
    entries = plan["entries"]
    moved = []
    try:
        if entries:
            mkdir_readable(archive_dir, parents=True)
        for entry in entries:
            source = lte_dir / entry["name"]
            info = source.lstat()
            is_link = stat.S_ISLNK(info.st_mode)
            kind = "Symlink" if is_link else "File"
            target = os.readlink(source) if is_link else ""
            if ((not is_link and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1))
                    or kind != entry["kind"] or target != entry["target"]
                    or (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_dev, info.st_ino)
                    != tuple(entry[key] for key in FILE_SIGNATURE_KEYS)):
                raise LteCleanupError(f"LTE temporary file changed while cleaning: {source.name}")
            destination = archive_dir / source.name
            os.replace(source, destination)
            moved.append(source.name)
            make_readable(destination)
    except (OSError, LteCleanupError):
        restore_lte_temporaries(lte_dir, archive_dir, moved)
        raise
    return {"removed_count": len(moved), "removed_files": moved, "total_size": plan["total_size"],
            "human_size": plan["human_size"], "archive_path": str(archive_dir) if moved else None}


def restore_lte_temporaries(lte_dir: Path, archive_dir: Path, names: list[str]) -> None:
    for name in reversed(names):
        source = archive_dir / name
        destination = lte_dir / name
        if destination.exists() or destination.is_symlink():
            raise LteCleanupError(f"Cannot restore LTE temporary file over an existing path: {name}")
        os.replace(source, destination)
