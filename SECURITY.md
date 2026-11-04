# Security Policy

## Supported Scope

Security reports are welcome for the current default branch. This project is an early-stage utility and does not yet publish formal release support guarantees.

## Reporting a Vulnerability

Please do not publish exploitable vulnerability details in a public issue. Use GitHub's private vulnerability reporting feature for this repository if it is enabled. If private reporting is unavailable, contact the maintainer through the public GitHub profile and request a private reporting channel.

Include:
- A concise description and potential impact.
- The affected commit or file path.
- Reproduction steps that do not expose personal data.
- Any suggested mitigation.

Please allow reasonable time for investigation and remediation before public disclosure.

## Safe-Use Guidance

- Run a dry scan before every cleanup operation.
- Review the target scope and retain backups of important files.
- Do not run the tool with elevated privileges unless a future documented feature explicitly requires it.
- Do not modify the cleanup roots to point at Windows system directories or another user's profile.
- Treat logs and JSON reports as potentially sensitive because paths may contain account or device information.

## Design Limitations

The cleaner only targets regular files in the current user's temporary directories. It does not claim to securely erase data, bypass file locks, clean the registry, remove malware, or repair Windows. File deletion is not a secure-erasure guarantee.
