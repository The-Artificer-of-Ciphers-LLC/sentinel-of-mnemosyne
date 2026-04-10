# Security Policy

## Supported Versions

Sentinel of Mnemosyne is in early development (pre-v1.0). Security fixes are applied to the `main` branch only.

| Version | Supported |
|---------|-----------|
| main    | Yes       |
| older   | No        |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Use GitHub's built-in **Private Vulnerability Reporting**:

1. Go to the [Security tab](https://github.com/The-Artificer-of-Ciphers-LLC/sentinel-of-mnemosyne/security)
2. Click **"Report a vulnerability"**
3. Fill in the details — describe the issue, affected component, and steps to reproduce

Private reports are visible only to maintainers. We will acknowledge receipt within 7 days and aim to resolve or mitigate within 30 days.

## What to Include

A useful report includes:
- The affected component (Sentinel Core, Pi harness, an interface, a module)
- Steps to reproduce the issue
- Potential impact
- Any suggested fix (optional but appreciated)

## Scope

This project is designed for **personal, self-hosted, local-network use**. The threat model reflects that — shared-secret auth (`X-Sentinel-Key`) is intentional and sufficient for the target deployment. Vulnerabilities that only affect intentionally insecure configurations are out of scope.

## Disclosure Timeline

We follow coordinated disclosure: please give us a reasonable window (30 days) to address the issue before publishing details publicly.
