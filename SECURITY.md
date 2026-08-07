# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability, **please do not file a public Issue**.

Report it privately via GitHub's "Report a vulnerability" feature:
https://github.com/killian99cm/anchor-system/security/advisories/new

## Data Security

The core of this project's security is **protecting personal holdings data**:

### Local Users
1. `.gitignore` already excludes all sensitive data files
2. Run `git status` to confirm no sensitive files are accidentally staged
3. Do not paste holdings data in Issues/PRs/Discussions

### Fork Users
1. Confirm `.gitignore` is in effect immediately after forking
2. Check for sensitive data before your first push
3. Use `portfolio_data_example.json` instead of real data

## Supported Versions

| Version | Support Status |
|------|:--:|
| v3.3 | ✅ Current |
| v3.2 | ❌ No longer maintained |
| v3.1 | ❌ No longer maintained |

## CI/CD Security

- GitHub Actions uses pinned versions (not `@latest`)
- Push operations restrict file paths to prevent accidental overwrites
