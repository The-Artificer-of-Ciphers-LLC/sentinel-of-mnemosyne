# Branch Protection (main)

Main branch protection is enforced.

## Current policy

- Require pull request before merge
- Require 1 approving review
- Require CODEOWNERS review
- Require approval of the most recent push
- Dismiss stale approvals on new commits
- Require status checks: `test`, `docker-build`
- Require branches to be up to date before merging
- Require conversation resolution before merge
- Require linear history
- Disallow force pushes and branch deletion
- Enforce for admins
- Restrict who can push/merge to `@trek-e`

## Update command

```bash
gh api repos/The-Artificer-of-Ciphers-LLC/sentinel-of-mnemosyne/branches/main/protection \
  --method PUT --input branch-protection.json
```
