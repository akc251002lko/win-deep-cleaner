# Contributing

Thank you for helping improve Win Deep Cleaner.

## Before submitting changes

1. Open an issue describing the bug or proposed improvement.
2. Keep runtime dependencies within the Python standard library.
3. Preserve the safety boundary: cleanup targets must remain restricted to validated temporary directories owned by the current user.
4. Never add broad deletion targets, recursive system-directory cleanup, or silent destructive defaults.
5. Add or update unit tests for path validation, cleanup decisions, error handling, and platform detection.
6. Run the complete test suite on Windows before submitting a pull request:

   `python -m unittest discover -s tests -v`

## Pull requests

Describe the user impact, affected Windows/Python versions, tests performed, and any limitations. Do not claim legacy Windows compatibility without testing on that Windows release in a disposable environment.

## Security issues

Do not disclose exploitable vulnerabilities in public issues. Follow the reporting guidance in [SECURITY.md](SECURITY.md).
