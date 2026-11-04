"""Unit tests for Win Deep Cleaner; no Windows APIs or third-party packages required."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import win_deep_cleaner as cleaner  # noqa: E402


class PlatformDetectionTests(unittest.TestCase):
    def test_detects_windows_11(self) -> None:
        version = SimpleNamespace(
            major=10, minor=0, build=22631, service_pack=""
        )
        with mock.patch.object(cleaner.os, "name", "nt"):
            with mock.patch.object(sys, "getwindowsversion", create=True, return_value=version):
                info = cleaner.detect_platform()
        self.assertEqual(info["os"], "Windows 11")

    def test_requires_service_pack_one_on_windows_7(self) -> None:
        version = SimpleNamespace(
            major=6, minor=1, build=7600, service_pack=""
        )
        with mock.patch.object(cleaner.os, "name", "nt"):
            with mock.patch.object(sys, "getwindowsversion", create=True, return_value=version):
                with self.assertRaises(cleaner.UnsupportedPlatformError):
                    cleaner.detect_platform()

    def test_accepts_windows_7_service_pack_one(self) -> None:
        version = SimpleNamespace(
            major=6, minor=1, build=7601, service_pack="Service Pack 1"
        )
        with mock.patch.object(cleaner.os, "name", "nt"):
            with mock.patch.object(sys, "getwindowsversion", create=True, return_value=version):
                info = cleaner.detect_platform()
        self.assertEqual(info["os"], "Windows 7")


class CleanerUtilityTests(unittest.TestCase):
    def test_format_bytes(self) -> None:
        self.assertEqual(cleaner.format_bytes(0), "0.00 B")
        self.assertEqual(cleaner.format_bytes(1024), "1.00 KB")

    def test_get_cleanup_roots_deduplicates_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.dict(os.environ, {"TEMP": temp_dir, "TMP": temp_dir}):
                with mock.patch.object(cleaner.tempfile, "gettempdir", return_value=temp_dir):
                    roots = cleaner.get_cleanup_roots()
            self.assertEqual(len(roots), 1)
            self.assertEqual(roots[0], Path(temp_dir).resolve())

    def test_scan_finds_only_old_regular_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_file = root / "old.tmp"
            new_file = root / "new.tmp"
            old_file.write_text("old", encoding="utf-8")
            new_file.write_text("new", encoding="utf-8")
            old_time = time.time() - 7200
            os.utime(str(old_file), (old_time, old_time))
            with mock.patch.object(cleaner, "get_cleanup_roots", return_value=[root]):
                result, candidates = cleaner.scan(1)
            self.assertEqual(result.files_found, 1)
            self.assertEqual([item[0] for item in candidates], [old_file])
            self.assertEqual(result.bytes_found, 3)

    def test_clean_defaults_to_dry_run_and_preserves_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate = root / "aged.tmp"
            candidate.write_text("keep for dry run", encoding="utf-8")
            old_time = time.time() - 7200
            os.utime(str(candidate), (old_time, old_time))
            with mock.patch.object(cleaner, "get_cleanup_roots", return_value=[root]):
                result = cleaner.clean(1, apply_changes=False)
            self.assertTrue(result.dry_run)
            self.assertEqual(result.files_considered, 1)
            self.assertEqual(result.files_deleted, 0)
            self.assertTrue(candidate.exists())

    def test_apply_deletes_eligible_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidate = root / "aged.tmp"
            candidate.write_text("delete me", encoding="utf-8")
            old_time = time.time() - 7200
            os.utime(str(candidate), (old_time, old_time))
            with mock.patch.object(cleaner, "get_cleanup_roots", return_value=[root]):
                result = cleaner.clean(1, apply_changes=True)
            self.assertFalse(result.dry_run)
            self.assertEqual(result.files_deleted, 1)
            self.assertEqual(result.bytes_deleted, len("delete me"))
            self.assertFalse(candidate.exists())

    def test_candidate_revalidation_detects_changed_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "changing.tmp"
            candidate.write_text("before", encoding="utf-8")
            original = candidate.lstat()
            candidate.write_text("after content", encoding="utf-8")
            self.assertFalse(cleaner._still_same_file(candidate, original))

    def test_json_report_contains_result_and_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = Path(temp_dir) / "report.json"
            result = cleaner.CleanupResult(dry_run=True, files_considered=2)
            cleaner.write_report(result, str(report))
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["files_considered"], 2)
            self.assertIn("generated_at_utc", payload)

    def test_cleanup_roots_reject_arbitrary_profile_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            profile = Path(temp_dir) / "profile"
            unsafe = profile / "Documents"
            unsafe.mkdir(parents=True)
            with mock.patch.dict(
                os.environ,
                {
                    "USERPROFILE": str(profile),
                    "TEMP": str(unsafe),
                    "TMP": str(unsafe),
                },
            ):
                with mock.patch.object(cleaner.tempfile, "gettempdir", return_value=str(unsafe)):
                    with self.assertRaises(cleaner.CleanerError):
                        cleaner.get_cleanup_roots()

    def test_clean_preserves_scan_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "aged.tmp"
            candidate.write_text("dry-run", encoding="utf-8")
            original = candidate.lstat()
            scan_result = cleaner.ScanResult(
                files_found=1,
                bytes_found=7,
                files_skipped=2,
                errors=1,
            )
            with mock.patch.object(
                cleaner,
                "scan",
                return_value=(scan_result, [(candidate, original)]),
            ):
                result = cleaner.clean(24, apply_changes=False)
            self.assertEqual(result.bytes_found, 7)
            self.assertEqual(result.files_skipped, 2)
            self.assertEqual(result.errors, 1)
            self.assertEqual(result.files_considered, 1)
            self.assertTrue(candidate.exists())

    def test_invalid_age_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            cleaner.scan(0)


if __name__ == "__main__":
    unittest.main()
