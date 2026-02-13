#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


DEFAULT_DATABASE_URL = "https://www.unige.ch/sciences/astro/evolution/en/database"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "geneva"
DEFAULT_EXTENSIONS = [
    ".dat",
    ".txt",
    ".tgz",
    ".tar",
    ".tar.gz",
    ".zip",
    ".gz",
]
USER_AGENT = "cmfgen-viewer-geneva-fetcher/1.0"


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.append(value.strip())
                break


@dataclass
class FetchStats:
    downloaded: int = 0
    skipped_existing: int = 0
    skipped_filtered: int = 0
    failed: int = 0


def _decode_html(payload: bytes) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def _fetch_bytes(url: str, timeout: float) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def _fetch_links(url: str, timeout: float) -> list[str]:
    payload = _fetch_bytes(url, timeout)
    parser = _LinkCollector()
    parser.feed(_decode_html(payload))
    return parser.links


def _discover_directory_urls(database_url: str, timeout: float) -> list[str]:
    links = _fetch_links(database_url, timeout)
    found: set[str] = set()
    for href in links:
        absolute = urljoin(database_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if "obswww.unige.ch" not in parsed.netloc.lower():
            continue
        if "/Research/evol/" not in parsed.path:
            continue
        if "." in parsed.path.rsplit("/", 1)[-1]:
            continue
        normalized = absolute if absolute.endswith("/") else f"{absolute}/"
        found.add(normalized)
    return sorted(found)


def _allowed_file(name: str, extensions: list[str], all_files: bool) -> bool:
    if all_files:
        return True
    lowered = name.lower()
    return any(lowered.endswith(ext.lower()) for ext in extensions)


def _target_path(output_dir: Path, file_url: str) -> Path:
    path = urlparse(file_url).path
    marker = "/Research/evol/"
    if marker in path:
        relative = path.split(marker, 1)[1].lstrip("/")
    else:
        relative = path.lstrip("/")
    return output_dir / relative


def _download_file(
    file_url: str,
    destination: Path,
    timeout: float,
    force: bool,
    dry_run: bool,
) -> bool:
    if destination.exists() and not force:
        return False
    if dry_run:
        return True

    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(file_url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        with destination.open("wb") as out:
            while True:
                chunk = response.read(1024 * 64)
                if not chunk:
                    break
                out.write(chunk)
    return True


def _crawl_directory(
    directory_url: str,
    timeout: float,
    max_depth: int,
    extensions: list[str],
    all_files: bool,
    output_dir: Path,
    force: bool,
    dry_run: bool,
    stats: FetchStats,
    visited_dirs: set[str],
    visited_files: set[str],
    depth: int = 0,
) -> None:
    normalized_dir = directory_url if directory_url.endswith("/") else f"{directory_url}/"
    if normalized_dir in visited_dirs:
        return
    visited_dirs.add(normalized_dir)

    print(f"[scan] {normalized_dir}")
    try:
        links = _fetch_links(normalized_dir, timeout)
    except Exception as exc:  # pragma: no cover - network errors are runtime/environment dependent
        stats.failed += 1
        print(f"[error] Failed to read directory index {normalized_dir}: {exc}")
        return

    for href in links:
        if not href or href.startswith("#") or href.startswith("?"):
            continue
        if href.startswith("../"):
            continue

        absolute = urljoin(normalized_dir, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if "obswww.unige.ch" not in parsed.netloc.lower():
            continue
        if "/Research/evol/" not in parsed.path:
            continue

        if absolute.endswith("/"):
            if depth < max_depth:
                _crawl_directory(
                    absolute,
                    timeout=timeout,
                    max_depth=max_depth,
                    extensions=extensions,
                    all_files=all_files,
                    output_dir=output_dir,
                    force=force,
                    dry_run=dry_run,
                    stats=stats,
                    visited_dirs=visited_dirs,
                    visited_files=visited_files,
                    depth=depth + 1,
                )
            continue

        file_name = Path(parsed.path).name
        if not _allowed_file(file_name, extensions, all_files):
            stats.skipped_filtered += 1
            continue

        if absolute in visited_files:
            continue
        visited_files.add(absolute)

        target = _target_path(output_dir, absolute)
        try:
            changed = _download_file(
                absolute,
                target,
                timeout=timeout,
                force=force,
                dry_run=dry_run,
            )
            if changed:
                stats.downloaded += 1
                action = "would download" if dry_run else "downloaded"
                print(f"[ok] {action}: {target}")
            else:
                stats.skipped_existing += 1
                print(f"[skip] exists: {target}")
        except Exception as exc:  # pragma: no cover - network errors are runtime/environment dependent
            stats.failed += 1
            print(f"[error] Failed to download {absolute}: {exc}")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download Geneva stellar-evolution track files into data/geneva. "
            "By default, directory URLs are auto-discovered from the UNIGE database page."
        )
    )
    parser.add_argument(
        "--database-url",
        default=DEFAULT_DATABASE_URL,
        help=f"Geneva database page URL used for discovery (default: {DEFAULT_DATABASE_URL}).",
    )
    parser.add_argument(
        "--dir",
        dest="seed_dirs",
        action="append",
        default=[],
        help="Explicit Geneva track directory URL to download from. Can be passed multiple times.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Destination directory (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=1,
        help="How deep to recurse into subdirectories under each seed directory (default: 1).",
    )
    parser.add_argument(
        "--ext",
        dest="extensions",
        action="append",
        default=[],
        help=(
            "Additional file extension filter to include (e.g. --ext .fits). "
            "Defaults already include: " + ", ".join(DEFAULT_EXTENSIONS)
        ),
    )
    parser.add_argument(
        "--all-files",
        action="store_true",
        help="Disable extension filtering and download all files found in scanned directories.",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds (default: 30).")
    parser.add_argument("--force", action="store_true", help="Re-download files even if destination exists.")
    parser.add_argument("--dry-run", action="store_true", help="List what would be downloaded, without writing files.")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir.expanduser().resolve()

    extensions = sorted(set(DEFAULT_EXTENSIONS + [ext.strip() for ext in args.extensions if ext.strip()]))
    if not args.seed_dirs:
        print(f"[info] discovering directory URLs from: {args.database_url}")
        try:
            seed_dirs = _discover_directory_urls(args.database_url, args.timeout)
        except Exception as exc:  # pragma: no cover - network errors are runtime/environment dependent
            print(f"[error] Failed to discover directories: {exc}")
            return 1
    else:
        seed_dirs = [url.strip() for url in args.seed_dirs if url.strip()]

    if not seed_dirs:
        print("[error] No Geneva directories found. Provide --dir URL manually.")
        return 1

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[info] output directory: {output_dir}")
    print(f"[info] seed directories: {len(seed_dirs)}")
    print(f"[info] max depth: {max(args.max_depth, 0)}")
    if args.all_files:
        print("[info] file filter: all files")
    else:
        print(f"[info] file filter: {', '.join(extensions)}")

    stats = FetchStats()
    visited_dirs: set[str] = set()
    visited_files: set[str] = set()

    for directory_url in seed_dirs:
        _crawl_directory(
            directory_url,
            timeout=args.timeout,
            max_depth=max(args.max_depth, 0),
            extensions=extensions,
            all_files=args.all_files,
            output_dir=output_dir,
            force=args.force,
            dry_run=args.dry_run,
            stats=stats,
            visited_dirs=visited_dirs,
            visited_files=visited_files,
            depth=0,
        )

    print(
        "[done] downloaded={0} skipped_existing={1} skipped_filtered={2} failed={3}".format(
            stats.downloaded,
            stats.skipped_existing,
            stats.skipped_filtered,
            stats.failed,
        )
    )
    return 0 if stats.failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
