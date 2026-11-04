# Win Deep Cleaner

[![CI](https://github.com/akc251002lko/win-deep-cleaner/actions/workflows/ci.yml/badge.svg)](https://github.com/akc251002lko/win-deep-cleaner/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)](https://www.microsoft.com/windows)

A conservative Windows temporary-file cleaner with a command-line interface (CLI) and a lightweight Tkinter graphical interface (GUI). The initial implementation focuses on user-scoped `TEMP` and `TMP` directories. It does not attempt registry cleaning, browser-profile cleaning, Windows Update cleanup, system-folder deletion, or broad disk optimisation.

> **Safety first:** scanning is the default. Files are only deleted when the user explicitly supplies `--apply` in the CLI or confirms the GUI action.

## What This Repository Is For

This repository contains the source code, tests, documentation, and continuous-integration workflow for Win Deep Cleaner. Its purpose is to provide a transparent, conservative utility for identifying aged files in the current user's temporary directories and optionally deleting eligible regular files.

The project is designed around least privilege and predictable behaviour. It does not require administrator rights for its supported user-temp cleanup scope.

## How To Use

### Requirements

- Microsoft Windows.
- Python 3.8 or newer for the current source code.
- Tkinter is required only for the GUI and is normally included with standard Windows Python installers.
- No third-party Python packages are required.

**Operating-system/runtime mapping:**
- Windows 7 SP1 and Windows 8: Python 3.8 is the legacy runtime line; the final regular Windows installer was Python 3.8.10. Python 3.8 is end-of-life and receives no security fixes.
- Windows 8.1: use Python 3.12 or an application package built with a compatible runtime.
- Windows 10 and Windows 11: use a currently supported Python release. The CI matrix checks Python 3.12 and 3.14, plus the legacy Python 3.8 line.

Do not expose Windows 7/8 devices to untrusted networks merely to run this utility. The source compatibility target does not constitute certification on every Windows release or architecture.

### CLI

Run commands from the repository root:

```powershell
python src/win_deep_cleaner.py
```

The default command performs a dry run and deletes nothing.

Scan files older than 48 hours:

```powershell
python src/win_deep_cleaner.py --age-hours 48
```

Write a JSON report:

```powershell
python src/win_deep_cleaner.py --age-hours 24 --report cleaner-report.json
```

Actually delete eligible files after reviewing the dry-run output:

```powershell
python src/win_deep_cleaner.py --age-hours 24 --apply
```

Show all CLI options:

```powershell
python src/win_deep_cleaner.py --help
```

### GUI

Launch the graphical interface:

```powershell
python src/win_deep_cleaner.py --gui
```

Use **Scan / Dry Run** first. Select **Clean Now** only after reviewing the scope and confirming the deletion prompt.

## Safety Model

- Only resolved `TEMP`, `TMP`, and Python temporary directory roots inside the current user's profile are considered.
- A candidate root must be a dedicated `Temp`/`Tmp` directory (including generated `tmp...` temporary folders); arbitrary profile folders, profile roots, drive roots, and system temporary directories are rejected.
- Duplicate roots are removed before scanning.
- Scan byte totals, skipped-file counts, and scan errors are preserved in CLI/GUI summaries and JSON reports.
- Only regular files older than the configured age are eligible.
- Symbolic links and Windows reparse points are skipped; directory traversal does not follow links.
- Directories are never deleted.
- Each candidate is revalidated immediately before deletion using file identity and metadata checks.
- Dry-run is the default; destructive CLI operation requires `--apply`.
- Logs use rotating files under the user's local application-data directory, with a temporary-directory fallback.
- JSON reports are written only when a report path is explicitly supplied.

No filesystem cleaner can guarantee that a file is safe to remove merely because it is old. Close applications before cleaning, review dry-run results, and keep backups of important data. Files in use or protected by Windows may fail to delete; such failures are reported rather than forcefully bypassed.

## Compatibility Matrix

| Windows target | Intended architecture targets | Validation status |
|---|---|---|
| Windows 7 SP1 | x86 and x64 | Legacy target; requires a compatible legacy Python runtime and real-device testing |
| Windows 8 | x86 and x64 | Target; requires real-device testing |
| Windows 8.1 | x86 and x64 | Target; Python 3.12 runtime; requires real-device testing |
| Windows 10 | x86 and x64 | Target; maintained-runtime CI coverage is x64; x86 requires real-device testing |
| Windows 11 | x64 | Target; CI coverage is limited to hosted Windows runners |

Windows 11 does not have an officially supported 32-bit x86 edition. ARM64 is not currently claimed as a validated target. GitHub-hosted CI does not run Windows 7, Windows 8, or Windows 8.1; compatibility with those systems and Windows x86 configurations must be verified on dedicated test machines before a release is described as certified.

## Development and Tests

The project uses only the Python standard library. Run the test suite from the repository root:

```powershell
python -m unittest discover -s tests -v
```

Compile-check the source and tests:

```powershell
python -m compileall -q src tests
```

GitHub Actions runs these checks on a Windows runner across selected Python and interpreter architectures. CI success is useful evidence, but it does not replace testing on each operating-system version in the compatibility matrix.

## Project Structure

```text
.
├── .github/
│   └── workflows/
│       └── ci.yml
├── src/
│   └── win_deep_cleaner.py
├── tests/
│   └── test_win_deep_cleaner.py
├── .gitignore
├── README.md
└── SECURITY.md
```

## Security

Please review [SECURITY.md](SECURITY.md) for safe-use guidance and vulnerability reporting.

## Telegram Community

For project announcements, repository updates, technical discussions, questions, and collaboration, join the [Telegram community](https://t.me/githubakc251002lko).

## Roadmap

- Expand automated tests for filesystem edge cases and Windows-specific behaviour.
- Validate the compatibility matrix on dedicated Windows versions and architectures.
- Improve scan summaries and reporting without expanding cleanup scope unsafely.
- Add further cleanup categories only with explicit scope, safeguards, and tests.

## Maintainer

Maintained by [akc251002lko](https://github.com/akc251002lko).
