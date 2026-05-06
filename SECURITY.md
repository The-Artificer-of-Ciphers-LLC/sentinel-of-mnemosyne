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

Private reports are visible only to maintainers. We will acknowledge receipt within **72 hours** and aim to provide an initial triage decision within **7 days**.

## What to Include

A useful report includes:
- The affected component (Sentinel Core, Pi harness, an interface, a module)
- Steps to reproduce the issue
- Potential impact
- Any suggested fix (optional but appreciated)

## Severity and Response Targets

- **Critical** (RCE, auth bypass, secret exposure): target mitigation within 7 days
- **High** (privilege escalation, significant data exposure): target mitigation within 14 days
- **Medium/Low**: handled in normal release cadence

## Scope

This project is designed for **personal, self-hosted, local-network use**. The threat model reflects that — shared-secret auth (`X-Sentinel-Key`) is intentional and sufficient for target deployment.

In scope:
- Vulnerabilities in default/recommended deployment docs
- Auth bypasses, command injection, SSRF, path traversal, secret leakage
- Supply-chain risks introduced by project-managed dependencies/workflows

Out of scope:
- Findings that require local machine compromise first
- Vulnerabilities in third-party services outside this repo (report upstream)
- Intentionally insecure local test/dev configurations

## Coordinated Disclosure

Please allow time for a fix before public disclosure.

- Default disclosure window: **30 days**
- If actively exploited or critical, we may request a shorter or staged disclosure plan
