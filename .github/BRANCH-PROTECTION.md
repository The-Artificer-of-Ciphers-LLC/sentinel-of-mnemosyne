# Branch Protection Setup

Main branch protection is not yet enforced. Run the following command when ready to enable it:

```bash
gh api repos/The-Artificer-of-Ciphers-LLC/sentinel-of-mnemosyne/branches/main/protection \
  --method PUT \
  --field required_status_checks=null \
  --field enforce_admins=false \
  --field required_pull_request_reviews='{"required_approving_review_count":1,"dismiss_stale_reviews":true}' \
  --field restrictions=null \
  --field allow_force_pushes=false \
  --field allow_deletions=false
```

## What This Enforces

- 1 required approving review before merge
- Stale review dismissal on new commits
- No force pushes to main
- No branch deletion

## What It Does NOT Enforce (yet)

- Required status checks (add after CI is set up)
- Admin enforcement (`enforce_admins=false` lets maintainers push directly during v0.x)

Enable admin enforcement when the project is past early development.
