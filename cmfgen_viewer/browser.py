from __future__ import annotations

from datetime import datetime, timezone
import mimetypes
from pathlib import Path

from .parsers import parse_known_file

CORE_FILES = {
    "RVTJ",
    "OBSFLUX",
    "MOD_SUM",
    "MEANOPAC",
    "HYDRO",
    "GAMMAS",
}

OPTIONAL_FILES = {
    "NETRATE",
    "TOTRATE",
    "EWDATA",
    "LINEHEAT",
    "J_COMP",
    "NON_THERM_COOL",
    "GAMFLUX",
    "GAMRAY_ENERGY_DEP",
    "WARNINGS",
    "OUTGEN",
    "STEQ_VALS",
}

RESTART_INTERNAL_FILES = {
    "SCRTEMP",
    "POINT1",
    "POINT2",
    "BAMAT",
    "BAMATPNT",
    "EDDFACTOR",
    "ES_J_CONV",
    "JH_AT_CURRENT_TIME",
    "JEW",
}

TEXT_EXTENSIONS = {
    ".txt",
    ".log",
    ".dat",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".md",
    ".out",
}

MAX_TEXT_PREVIEW_BYTES = 512 * 1024


def resolve_path(basepath: str, relpath: str = "") -> Path:
    base = Path(basepath).expanduser().resolve()
    target = (base / relpath).resolve()

    try:
        target.relative_to(base)
    except ValueError as exc:
        raise FileNotFoundError(relpath) from exc

    return target


def make_breadcrumb(path: str, base_name: str = "ROOT") -> list[dict[str, str | None]]:
    parts = [part for part in Path(path).parts if part not in ("", ".")]
    if not parts:
        return [{"name": base_name, "path": None}]

    breadcrumb: list[dict[str, str | None]] = [{"name": base_name, "path": ""}]
    cursor: list[str] = []
    for part in parts:
        cursor.append(part)
        breadcrumb.append({"name": part, "path": "/".join(cursor)})

    breadcrumb[-1]["path"] = None
    return breadcrumb


def _join_relpath(parent: str, child: str) -> str:
    if not parent:
        return child
    return f"{parent.rstrip('/')}/{child}"


def classify_cmfgen_role(filename: str) -> str:
    name = filename.upper()
    if name in CORE_FILES:
        return "core_viewer"
    if name in OPTIONAL_FILES or name.startswith("POP") or name.endswith("OUT"):
        return "optional_diagnostic"
    if name in RESTART_INTERNAL_FILES or name.endswith("_INFO"):
        return "restart_internal"
    return "other"


def _is_text_like_file(path: Path, mime: str | None, role: str) -> bool:
    if mime and mime.startswith("text/"):
        return True
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    if role in {"core_viewer", "optional_diagnostic"}:
        return True

    try:
        with path.open("rb") as handle:
            chunk = handle.read(4096)
    except OSError:
        return False

    if b"\x00" in chunk:
        return False

    try:
        chunk.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _classify_kind(path: Path, mime: str | None, role: str) -> str:
    if path.is_dir():
        return "dir"
    if mime and mime.startswith("image/"):
        return "image"
    if _is_text_like_file(path, mime, role):
        return "text"
    return "file"


def _human_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    unit = units[0]
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            break
        value /= 1024.0
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


def list_directory(basepath: str, relpath: str = "", show_all: bool = False) -> list[dict[str, object]]:
    directory = resolve_path(basepath, relpath)
    if not directory.is_dir():
        raise NotADirectoryError(str(directory))

    entries: list[dict[str, object]] = []
    for entry in directory.iterdir():
        if entry.name.startswith(".") and not show_all:
            continue

        try:
            stat = entry.stat()
        except OSError:
            continue

        rel = _join_relpath(relpath, entry.name)
        mime = mimetypes.guess_type(entry.name)[0]
        role = classify_cmfgen_role(entry.name)
        kind = _classify_kind(entry, mime, role)
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        entries.append(
            {
                "name": entry.name,
                "path": rel,
                "is_dir": entry.is_dir(),
                "kind": kind,
                "mime": mime or "application/octet-stream",
                "cmfgen_role": role,
                "size": stat.st_size,
                "human_size": _human_size(stat.st_size),
                "modified_iso": modified_at.isoformat(),
                "modified_display": modified_at.strftime("%Y-%m-%d %H:%M:%S"),
                "modified_ts": stat.st_mtime,
            }
        )

    entries.sort(key=lambda item: (not bool(item["is_dir"]), str(item["name"]).lower()))
    return entries


def _text_preview(path: Path, max_bytes: int = MAX_TEXT_PREVIEW_BYTES) -> tuple[str, bool]:
    with path.open("rb") as handle:
        payload = handle.read(max_bytes + 1)
    truncated = len(payload) > max_bytes
    payload = payload[:max_bytes]
    return payload.decode("utf-8", errors="replace"), truncated


def describe_file(basepath: str, relpath: str) -> dict[str, object]:
    target = resolve_path(basepath, relpath)
    if not target.is_file():
        raise FileNotFoundError(relpath)

    stat = target.stat()
    mime = mimetypes.guess_type(target.name)[0]
    role = classify_cmfgen_role(target.name)
    kind = _classify_kind(target, mime, role)
    modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

    context: dict[str, object] = {
        "name": target.name,
        "size": stat.st_size,
        "human_size": _human_size(stat.st_size),
        "modified_iso": modified_at.isoformat(),
        "modified_display": modified_at.strftime("%Y-%m-%d %H:%M:%S"),
        "modified_ts": stat.st_mtime,
        "mime": mime or "application/octet-stream",
        "cmfgen_role": role,
        "kind": kind,
        "mode": "download",
    }

    if kind == "text":
        contents, truncated = _text_preview(target)
        context["mode"] = "text"
        context["contents"] = contents
        context["truncated"] = truncated
        try:
            parsed = parse_known_file(target)
            if parsed is not None:
                context["parsed"] = parsed
        except Exception as exc:
            context["parse_error"] = str(exc)
    elif kind == "image":
        context["mode"] = "image"

    return context
