#!/usr/bin/env bash
# bootstrap.sh - Idempotent repo setup for repos created from clouatre-labs/template-exp-repo.
# Run from within the cloned repo: bash scripts/bootstrap.sh [--apply]
# Requires: gh CLI authenticated with repo write access (admin for --apply).
#
# --apply creates the repo branch ruleset directly instead of printing the
# command. Without it, the script prints the ruleset JSON for manual review.
#
# Labels are also managed org-wide by clouatre-labs/.github
# (apply-org-settings.sh, add/update-only); outside that org, this script is
# the label source of truth.

set -euo pipefail

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "")
if [ -z "$REPO" ]; then
  echo "ERROR: could not detect repo. Run this script from within the cloned repository."
  exit 1
fi

echo "Creating labels for ${REPO} ..."

create_label() {
  gh label create "$1" --color "$2" --description "$3" --repo "$REPO" --force
}

# GitHub defaults + issue-template vocabulary
create_label "bug"              "d73a4a" "Defect or unexpected behavior"
create_label "documentation"    "0075ca" "Documentation improvements"
create_label "duplicate"        "cfd3d7" "Duplicate issue or PR"
create_label "enhancement"      "a2eeef" "New feature or improvement"
create_label "good first issue" "7057ff" "Good for newcomers"
create_label "help wanted"      "008672" "Extra attention needed"
create_label "invalid"          "e4e669" "Not valid or out of scope"
create_label "question"         "d876e3" "Question or discussion"
create_label "wontfix"          "ffffff" "Will not be addressed"
# Conventional Commits types (.commitlintrc.yml)
create_label "build"            "1d76db" "Build system or external dependency changes"
create_label "chore"            "d4c5f9" "Maintenance and tooling"
create_label "ci"               "e6e6e6" "CI pipeline changes"
create_label "docs"             "0c2e6a" "Documentation-only change"
create_label "feat"             "a2eeef" "New feature (minor version bump)"
create_label "fix"              "d93f0b" "Bug fix (patch version bump)"
create_label "perf"             "f9d0c4" "Performance improvement"
create_label "refactor"         "fbca04" "Code change that neither fixes a bug nor adds a feature"
create_label "revert"           "e99695" "Reverts a previous commit"
create_label "style"            "c2e0c6" "Formatting or style change with no logic change"
create_label "test"             "5319e7" "Test-only change"
# Cross-cutting
create_label "dependencies"     "0366d6" "Dependency update (Renovate or manual)"
create_label "security"         "b60205" "Security fixes and hardening"
create_label "github_actions"   "000000" "Pull requests that update GitHub Actions code"

echo "Labels created (or updated if they already existed)."

echo ""
echo "Next step: the repo branch ruleset."
echo "Two layers apply: the org ruleset 'Main Branch Protection' already covers"
echo "this repo org-wide (clouatre-labs/.github); the repo ruleset below adds the"
echo "repo-specific required checks. It is the authoritative layer for adopters"
echo "outside the org."
echo ""

RULESET_BODY=$(cat <<EOF
{
  "name": "main-protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["refs/heads/main"],
      "exclude": []
    }
  },
  "bypass_actors": [
    {
      "actor_id": 5,
      "actor_type": "RepositoryRole",
      "bypass_mode": "pull_request"
    }
  ],
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "required_signatures"},
    {
      "type": "commit_message_pattern",
      "parameters": {
        "name": "DCO Sign-off",
        "operator": "contains",
        "pattern": "Signed-off-by:",
        "negate": false
      }
    },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "require_code_owner_review": true,
        "dismiss_stale_reviews_on_push": false,
        "require_last_push_approval": false,
        "allowed_merge_methods": ["squash"]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          {"context": "CI Result", "integration_id": null},
          {"context": "Security Result", "integration_id": null},
          {"context": "Lint markdown", "integration_id": null}
        ]
      }
    }
  ]
}
EOF
)

if [ "${1:-}" = "--apply" ]; then
  echo "Creating ruleset via API (requires repo admin access)..."
  gh api "repos/$REPO/rulesets" -X POST --input - <<<"$RULESET_BODY" --jq '.name + " (" + (.id | tostring) + ")"'
  echo "Ruleset created."
else
  echo "Run the following command (requires repo admin access), or re-run with --apply:"
  echo ""
  echo "gh api repos/$REPO/rulesets -X POST --input - <<'RULESET'"
  echo "$RULESET_BODY"
  echo "RULESET"
fi