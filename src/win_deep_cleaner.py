#!/usr/bin/env python3
"""Windows Deep Cleaner: conservative temporary-file cleanup for Windows 7–11.

Python source is kept compatible with Python 3.8 for legacy Windows deployments.
Cleanup is dry-run by default. Only files inside the current user's TEMP/TMP
directories are considered; directories and system locations are never removed.
"""
from __future__ import annotations

import argparse
import contextvars
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import platform
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

APP_NAME = "WinDeepCleaner"
DEFAULT_AGE_HOURS = 24
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3


class CleanerError(Exception):
    """Base exception for expected cleaner failures."""


class UnsupportedPlatformError(CleanerError):
    """Raised when the operating system is not supported."""


class SafetyViolationError(CleanerError):
    """Raised when a cleanup target fails a safety check."""


@dataclass
class ScanResult:
    files_found: int = 0
    bytes_found: int = 0
    files_skipped: int = 0
    errors: int = 0


@dataclass
class CleanupResult:
    dry_run: bool
    files_considered: int = 0
    bytes_found: int = 0
    files_deleted: int = 0
    bytes_deleted: int = 0
    files_skipped: int = 0
    errors: int = 0


SESSION_ID = contextvars.ContextVar("win_deep_cleaner_session_id", default="-")


class SessionIdFilter(logging.Filter):
    """Attach the active cleanup-session identifier to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = SESSION_ID.get()
        return True


def configure_logging() -> logging.Logger:
    logger = logging.getLogger(APP_NAME)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | session=%(session_id)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    try:
        log_dir = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
        log_dir = log_dir / APP_NAME / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            str(log_dir / "cleaner.log"),
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        handler = logging.StreamHandler()
    handler.addFilter(SessionIdFilter())
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


LOGGER = configure_logging()


def detect_platform() -> Dict[str, str]:
    if os.name != "nt":
        raise UnsupportedPlatformError("Win Deep Cleaner runs on Microsoft Windows only.")
    version = sys.getwindowsversion()
    major, minor, build = version.major, version.minor, version.build
    if major == 6 and minor == 1:
        name = "Windows 7"
        if not getattr(version, "service_pack", ""):
            raise UnsupportedPlatformError("Windows 7 Service Pack 1 is required.")
    elif major == 6 and minor == 2:
        name = "Windows 8"
    elif major == 6 and minor == 3:
        name = "Windows 8.1"
    elif major == 10 and build >= 22000:
        name = "Windows 11"
    elif major == 10:
        name = "Windows 10"
    else:
        raise UnsupportedPlatformError(
            "Unsupported Windows version: {}.{}.{}".format(major, minor, build)
        )
    architecture = "64-bit" if sys.maxsize > 2 ** 32 else "32-bit"
    return {
        "os": name,
        "version": "{}.{}.{}".format(major, minor, build),
        "architecture": architecture,
        "python": platform.python_version(),
    }


def get_cleanup_roots() -> List[Path]:
    """Return deduplicated TEMP/TMP folders strictly inside the user profile."""
    profile_value = os.environ.get("USERPROFILE")
    if not profile_value:
        raise CleanerError("USERPROFILE is unavailable; refusing to guess cleanup scope.")
    try:
        profile = Path(profile_value).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise CleanerError("The current user profile could not be resolved.") from exc

    candidates = [
        os.environ.get("TEMP"),
        os.environ.get("TMP"),
        tempfile.gettempdir(),
    ]
    roots: List[Path] = []
    seen = set()
    profile_key = os.path.normcase(str(profile))
    for candidate in candidates:
        if not candidate:
            continue
        try:
            path = Path(candidate).expanduser().resolve()
            path_key = os.path.normcase(str(path))
            try:
                common = os.path.commonpath([profile_key, path_key])
            except ValueError:
                common = ""
            # Never scan a profile root, a drive root, a system temp folder,
            # or an arbitrary user folder merely because TEMP was redirected.
            folder_name = path.name.lower()
            if (
                os.path.normcase(common) != profile_key
                or path_key == profile_key
                or not (folder_name in ("temp", "tmp") or folder_name.startswith("tmp"))
                or not path.is_dir()
                or is_reparse_point(path)
            ):
                LOGGER.warning("Ignoring unsafe or inaccessible temporary directory: %s", candidate)
                continue
            if path_key not in seen:
                seen.add(path_key)
                roots.append(path)
        except (OSError, RuntimeError):
            LOGGER.warning("Ignoring inaccessible temporary directory: %s", candidate)
    if not roots:
        raise CleanerError("No safe user-profile TEMP/TMP directory was found.")
    return roots


def is_reparse_point(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        reparse_flag = getattr(stat_module(), "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return bool(attributes & reparse_flag)
    except OSError:
        return True


def stat_module():
    # Kept local to avoid importing platform-specific constants on other systems.
    import stat
    return stat


def iter_candidate_files(
    root: Path,
    on_error: Optional[Callable[[OSError], None]] = None,
) -> Iterable[Path]:
    """Walk without following links and report inaccessible directories."""
    for current, directories, filenames in os.walk(
        str(root), topdown=True, followlinks=False, onerror=on_error
    ):
        current_path = Path(current)
        safe_directories = []
        for directory in directories:
            child = current_path / directory
            if child.is_symlink() or is_reparse_point(child):
                continue
            safe_directories.append(directory)
        directories[:] = safe_directories
        for filename in filenames:
            candidate = current_path / filename
            if candidate.is_symlink() or is_reparse_point(candidate):
                continue
            yield candidate


def scan(age_hours: int) -> Tuple[ScanResult, List[Tuple[Path, os.stat_result]]]:
    if age_hours < 1:
        raise ValueError("age-hours must be at least 1.")
    cutoff = time.time() - age_hours * 3600
    result = ScanResult()
    candidates: List[Tuple[Path, os.stat_result]] = []
    roots = get_cleanup_roots()
    if not roots:
        raise CleanerError("No accessible user temporary directory was found.")
    def record_walk_error(error: OSError) -> None:
        result.errors += 1
        LOGGER.warning("Could not traverse directory %s: %s", error.filename, error)

    for root in roots:
        for path in iter_candidate_files(root, record_walk_error):
            try:
                info = path.lstat()
                if not path.is_file() or info.st_mtime > cutoff:
                    result.files_skipped += 1
                    continue
                candidates.append((path, info))
                result.files_found += 1
                result.bytes_found += info.st_size
            except OSError as exc:
                result.errors += 1
                LOGGER.warning("Could not inspect %s: %s", path, exc)
    return result, candidates


def _still_same_file(path: Path, original: os.stat_result) -> bool:
    try:
        current = path.lstat()
        return (
            not path.is_symlink()
            and not is_reparse_point(path)
            and current.st_ino == original.st_ino
            and current.st_size == original.st_size
            and current.st_mtime_ns == original.st_mtime_ns
            and current.st_dev == original.st_dev
        )
    except OSError:
        return False


def clean_candidates(
    scan_result: ScanResult,
    candidates: Sequence[Tuple[Path, os.stat_result]],
    apply_changes: bool,
) -> CleanupResult:
    """Process a previously scanned candidate snapshot.

    The GUI uses this split-phase API to show the exact scan summary before
    asking for destructive confirmation. Candidate metadata is revalidated
    immediately before each deletion.
    """
    result = CleanupResult(
        dry_run=not apply_changes,
        files_considered=len(candidates),
        bytes_found=scan_result.bytes_found,
        files_skipped=scan_result.files_skipped,
        errors=scan_result.errors,
    )
    if apply_changes and scan_result.errors:
        raise CleanerError(
            "Cleanup was stopped because the scan was incomplete. "
            "Resolve the reported scan errors and scan again."
        )
    for path, original in candidates:
        if not apply_changes:
            continue
        if not _still_same_file(path, original):
            result.files_skipped += 1
            continue
        try:
            # Recheck immediately before unlinking; never recurse into directories.
            if not path.is_file():
                raise SafetyViolationError("Target is no longer a regular file.")
            path.unlink()
            result.files_deleted += 1
            result.bytes_deleted += original.st_size
            LOGGER.info("Deleted temporary file: %s", path)
        except (OSError, SafetyViolationError) as exc:
            result.errors += 1
            LOGGER.warning("Could not delete %s: %s", path, exc)
    return result


def clean(age_hours: int, apply_changes: bool) -> CleanupResult:
    scan_result, candidates = scan(age_hours)
    return clean_candidates(scan_result, candidates, apply_changes)


def write_report(result: CleanupResult, destination: Optional[str]) -> None:
    if not destination:
        return
    report_path = Path(destination).expanduser()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    payload["generated_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with report_path.open("w", encoding="utf-8") as report_file:
        json.dump(payload, report_file, indent=2)
        report_file.write("\n")


def format_bytes(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return "{:.2f} {}".format(amount, unit)
        amount /= 1024
    return "{} B".format(value)


def run_gui() -> int:
    """Load the GUI layer lazily so CLI use does not import Tkinter."""
    try:
        from .gui import run_gui as gui_runner
    except ImportError:
        from gui import run_gui as gui_runner
    return gui_runner()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="win-deep-cleaner",
        description="Safely scan and clean aged files in user TEMP/TMP directories.",
    )
    parser.add_argument("--gui", action="store_true", help="Launch the graphical interface.")
    parser.add_argument(
        "--age-hours",
        type=int,
        default=DEFAULT_AGE_HOURS,
        help="Minimum file age in hours (default: %(default)s).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete eligible files. Without this flag, performs a dry run.",
    )
    parser.add_argument("--report", help="Write a JSON report to this file path.")
    parser.add_argument("--version", action="version", version="Win Deep Cleaner 0.1.0")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    session_token = SESSION_ID.set(uuid.uuid4().hex[:12])
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        info = detect_platform()
        LOGGER.info(
            "Starting on %s %s (%s), Python %s",
            info["os"], info["version"], info["architecture"], info["python"],
        )
        if args.gui:
            return run_gui()
        result = clean(args.age_hours, args.apply)
        write_report(result, args.report)
        print(
            "{} | considered={} found_bytes={} deleted={} reclaimed={} skipped={} errors={}".format(
                "DRY RUN" if result.dry_run else "CLEANUP",
                result.files_considered,
                format_bytes(result.bytes_found),
                result.files_deleted,
                format_bytes(result.bytes_deleted),
                result.files_skipped,
                result.errors,
            )
        )
        if result.dry_run:
            print("No files were deleted. Re-run with --apply to perform cleanup.")
        return 1 if result.errors else 0
    except (CleanerError, ValueError) as exc:
        LOGGER.error("%s", exc)
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        LOGGER.warning("Operation cancelled by user.")
        print("Cancelled.", file=sys.stderr)
        return 130
    except Exception:
        LOGGER.exception("Unexpected fatal error")
        print("ERROR: unexpected failure; see the log for details.", file=sys.stderr)
        return 1
    finally:
        SESSION_ID.reset(session_token)


if __name__ == "__main__":
    sys.exit(main())
