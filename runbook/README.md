---
project: polymarket-tui
tier: 3
owner: byron
lifecycle: production
reviewed: 2026-09-01
---

# polymarket-tui runbook

Terminal client for Polymarket, shipped as a Python package (PyPI, Homebrew tap) with a static
landing page and a small content pipeline (daily blog post, daily email digest, an on-demand
short-video generator). Tier 3: nothing is kept alive. "Live" means people can get it:
`pip install polymarket-tui` and `brew install byronxlg/tap/polymarket-tui` resolve to the latest
release, and https://polymarket-tui.botsmith.dev/ serves. If everything below stopped, existing
installs keep working and no data is lost.

## Where it runs

Nothing runs on this Mac. The package lives on PyPI (published by GitHub Actions via Trusted
Publishing, no token stored) and is mirrored into the Homebrew tap
[byronxlg/homebrew-tap](https://github.com/byronxlg/homebrew-tap) by that repo's own daily
workflow. The landing page and blog are static files in `site/`, deployed to GitHub Pages behind
the `polymarket-tui.botsmith.dev` CNAME (the DNS record is in x402-services' Terraform, not here).
The newsletter is two Lambdas, a DynamoDB table and SES in AWS ap-southeast-2, managed by
`infra/newsletter/` Terraform and fired by an EventBridge Scheduler cron. Content crons run on
GitHub Actions in this repo. The app itself talks to Polymarket's public APIs from the user's own
machine; there is no server in between.

## Objectives

| Indicator | Target | Window | Measured by |
| --- | --- | --- | --- |
| Latest GitHub release is on PyPI within 1 h of publishing | every release | per release | `curl -s https://pypi.org/pypi/polymarket-tui/json \| jq -r .info.version` equals `gh release view --json tagName` minus the `v` |
| https://polymarket-tui.botsmith.dev/ returns 200 | 99% of checks | 30 days | `curl -s -o /dev/null -w '%{http_code}' https://polymarket-tui.botsmith.dev/` |
| Each enabled scheduled workflow's last run is within 2x its cadence | every cron | 7 days (weekly review) | `gh run list --workflow <file> --limit 1`; newsletter digest via CloudWatch `sent/failed/subscribers` line |

Recovery targets: RTO 14 days (projects.yaml `sla.restore`), RPO n/a. The only state this project
owns is the newsletter subscriber table; it is a DynamoDB table with no backup configured, and
losing it means subscribers re-subscribe.

## Who is watching

Nobody off-host. Monitor kind is `ci-only`: the only signals are GitHub's own scheduled-workflow
failure email, the `Report failure to Telegram` step in `daily-short.yml`, and the weekly fleet
review. `blog-post.yml` has no failure notification of its own. Known gap: GitHub disables
scheduled workflows after 60 days without repo activity, and nothing here would notice; the blog
cron is what keeps the repo active. Nothing checks that the site answers 200 or that the Homebrew
formula tracks PyPI between reviews.

## Files

| Question | File |
| --- | --- |
| How do changes reach users, how do I roll back? | [updates.md](updates.md) |

Tier 3 does not carry `health.md`, `recovery.md`, `dependencies.md` or `incidents/`. The
objectives table above is the health check; rollback is in `updates.md`.

## Schedules

| What | Where it runs | When | Notes |
| --- | --- | --- | --- |
| Daily blog post (`blog-post.yml`) | github-actions | `23 6 * * *` UTC | Claude Code writes a post from live Gamma data or `docs/blog-todo.md`, opens a PR, merges it if the diff is post-only, then dispatches `pages.yml`. Actual start times drift hours past the cron; that is GitHub, not a fault |
| Landing page deploy (`pages.yml`) | github-actions | push to `main` touching `site/**`, or dispatch | GitHub Pages; most runs are the blog job's dispatch, because merges made with `GITHUB_TOKEN` do not trigger it |
| Daily short (`daily-short.yml`) | github-actions | `41 21 * * *` UTC | Disabled manually 2026-08-14 when short production moved to the manual AI-clip pipeline (#202). Renders an mp4 of the real TUI with `SHORTS_MODE=anon` and sends it to Telegram; re-enable with `gh workflow enable daily-short.yml` |
| Newsletter digest | AWS EventBridge Scheduler, ap-southeast-2 | `cron(0 7 * * ? *)` Pacific/Auckland | one email to confirmed subscribers via SES; retries disabled on purpose (a retry would double-send). Not a GitHub workflow: `newsletter.yml` is the Terraform pipeline, not the schedule |
| Homebrew formula bump (`bump.yml`) | github-actions, repo `byronxlg/homebrew-tap` | `17 6 * * *` UTC | repoints the formula at the newest PyPI sdist; a release therefore reaches brew within about a day, or immediately with `gh workflow run bump.yml -R byronxlg/homebrew-tap` |
| Publish (`publish.yml`) | github-actions | on GitHub release published | tests, builds, uploads to PyPI |
| Newsletter Terraform (`newsletter.yml`) | github-actions | push to `main` under `infra/newsletter/**` (PRs plan only) | plan and apply in one run |

## Dashboards and logs

- Actions run history: https://github.com/byronxlg/polymarket-tui/actions ; per workflow
  `gh run list --workflow <file>.yml`.
- PyPI: https://pypi.org/project/polymarket-tui/ ; Homebrew tap runs:
  `gh run list -R byronxlg/homebrew-tap`.
- Newsletter: CloudWatch log groups for `polymarket-tui-newsletter-digest` and
  `polymarket-tui-newsletter-api` in ap-southeast-2; the digest writes one
  `sent/failed/subscribers` summary line per run. AWS Budgets emails at $3 and $5 monthly spend.
- Content log: `docs/marketing-log.md` records every outbound message; `docs/blog-todo.md`
  records shipped posts.
