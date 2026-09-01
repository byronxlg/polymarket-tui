---
project: polymarket-tui
reviewed: 2026-09-01
deploy_path: tag
rollback_minutes: 30
---

# Updates

Three things ship, by three paths, all through GitHub Actions and none from a laptop. The
package ships on a GitHub release: the version is whatever `pyproject.toml` says at the tagged
commit, and PyPI will not accept the same version twice, so a bad release is followed by a new
one, not a re-upload. The site ships on merge to `main`. The newsletter ships as Terraform,
including its Lambda code, on merge to `main`. Merging to `main` therefore deploys the site and
the newsletter but never the package; users only see app changes after a release.

## How a change reaches production

| Change to | Pipeline | Trigger | Lands in prod when | Evidence |
| --- | --- | --- | --- | --- |
| `src/**`, `pyproject.toml` (the package) | `publish.yml`: `uv run pytest`, `uv build`, `pypa/gh-action-pypi-publish` via OIDC (environment `pypi`) | `gh release create v<X.Y.Z>` after bumping `version` in `pyproject.toml` and tagging | PyPI shows the version, usually within 5 min | https://pypi.org/project/polymarket-tui/ ; `pip index versions polymarket-tui` |
| Homebrew | `bump.yml` in `byronxlg/homebrew-tap` rewrites the formula url and sha256 from PyPI | daily `17 6 * * *`, or `gh workflow run bump.yml -R byronxlg/homebrew-tap` | the tap commit lands | `brew info byronxlg/tap/polymarket-tui`; tap commit log |
| `site/**` (landing page, blog) | `pages.yml`: upload `site/`, `actions/deploy-pages` | push to `main` touching `site/**`; `workflow_dispatch` (what `blog-post.yml` uses) | deploy job finishes, about 1 min | `curl -sI https://polymarket-tui.botsmith.dev/`; the run's `page_url` |
| `infra/newsletter/**` (Terraform and Lambda `src/`) | `newsletter.yml`: fmt, validate, `plan -out`, `apply` of that plan | merge to `main` (PRs plan only) | apply step finishes | Actions log; next 07:00 NZ digest |
| `.github/workflows/*.yml`, `.claude/skills/blog-post/**` | none, read at run time | merge to `main` | the next scheduled run | that run's log |
| `Formula/polymarket-tui.rb` in this repo | nothing consumes it | n/a | never | It is a stale copy pinned to a 0.1.0 commit; the tap's formula is the one users install. Treat as history |

Not in the table:

- `install.sh` installs `git+https://github.com/byronxlg/polymarket-tui` at `main`, not the PyPI
  release, so a merge to `main` is immediately live for anyone using the curl one-liner or
  `brew install --HEAD`.
- The blog cron merges its own PRs (authorized 2026-07-17). A post that ships something other
  than post files is left as an open PR; that is the review point.
- GitHub Actions secrets change with `gh secret set`; nothing needs a redeploy to pick them up.

## Post-deploy smoke test

After a release, once `publish.yml` is green:

```sh
V=$(gh release view --repo byronxlg/polymarket-tui --json tagName -q .tagName | sed 's/^v//')
curl -s https://pypi.org/pypi/polymarket-tui/json | jq -r .info.version   # expect $V
uvx --refresh polymarket-tui@$V --version                                  # installs and prints $V
gh workflow run bump.yml -R byronxlg/homebrew-tap && sleep 90 && brew info byronxlg/tap/polymarket-tui | head -1
```

After a site deploy: `curl -s -o /dev/null -w '%{http_code}\n' https://polymarket-tui.botsmith.dev/`
returns 200 and the new post is linked from `/blog/`. After a newsletter apply: read the apply
log for the resource count, then the next digest's CloudWatch summary line. None of these are
merge gates; `publish.yml` runs the test suite before it uploads, which is the only gate.

## Rollback

- Package: yank the bad version on PyPI (`Manage project -> Releases -> Options -> Yank`;
  yanked versions are skipped by resolvers but existing pins still install), then bump
  `pyproject.toml` to a new patch version from the last good commit, tag and release again. Do
  not delete the release or retag an existing version; PyPI will reject the re-upload and the tap
  would point at a 404. Run the tap bump by hand afterwards so brew users move too.
- Site: `git revert` the merge and push to `main`; `pages.yml` redeploys. If the bad content came
  from the blog cron, revert its squash commit (the PR is the audit trail).
- Newsletter: `git revert` the Terraform or `src/` change and let `newsletter.yml` apply it.
  Never `terraform apply` locally, and never retry a digest run by hand: a second invocation
  sends the email again to everyone.

## Scheduled maintenance

| What | Cadence | How | Validated by |
| --- | --- | --- | --- |
| Python deps (`uv lock --upgrade`) | monthly | PR, `uv run pytest -q`, drive the app once in tmux (CLAUDE.md) | tests; the next release |
| Textual major versions | on release, deliberately | PR; the widget gotchas in CLAUDE.md are Textual-version-specific, expect focus and layout regressions | tmux walkthrough of home, market, portfolio, search |
| `py-clob-client-v2` bumps | on release | PR; read `docs/trading.md` first, run the order validation tests | `uv run pytest -q` |
| Python version (`.python-version`, `requires-python`, `python@3.12` in the formula, `python3.12` Lambda runtime) | when 3.12 is within 6 months of EOL (Oct 2028) | one PR across package, tap and `infra/newsletter/lambda.tf` | CI, a release, a digest run |
| GitHub Actions versions (`setup-uv`, `checkout`, `deploy-pages`, `claude-code-action`, `setup-terraform`) | when a run warns about a deprecated version | PR | the next scheduled run |
| `CLAUDE_CODE_OAUTH_TOKEN` | when `blog-post.yml` starts failing auth | `claude setup-token`, then `gh secret set CLAUDE_CODE_OAUTH_TOKEN` | next blog run |
| `polymarket-tui-ci` AWS access key | on suspicion of leak, otherwise not rotated | create second key via `doppler run --project global --config home -- aws iam create-access-key --user-name polymarket-tui-ci`, `gh secret set`, then delete the old one; never delete first | `newsletter.yml` plan on a no-op PR |
| Terraform providers (`.terraform.lock.hcl`) | quarterly | `terraform init -upgrade` locally, commit the lock, PR | plan shows no changes |
| Re-record `site/assets/demo.cast` | after visible UI changes | `bash scripts/record_demo.sh` (authed DRY, redacted; the script refuses to write if identity survives) | play the page locally |
| Scheduled-workflow liveness | weekly review | `gh workflow list --all` shows no unexpected `disabled_inactivity`; re-enable with `gh workflow enable <file>` | run history |

## Flags, arming and other runtime switches

| Switch | Lives in | Effect | Current value: how to check |
| --- | --- | --- | --- |
| `SHORTS_MODE=anon` | `daily-short.yml` env on the record step; `scripts/shorts/record.sh` | records signed out: no credentials file, no account screens, so CI can never place an order or show a balance | read the workflow; local runs default to authed DRY via `scripts/journey_env.sh` |
| `POLYMARKET_HIDE_BALANCES=1` | `scripts/journey_env.sh`, `record_demo.sh`, shorts scripts | masks header cash and own-position numbers at the source for recordings | set by the scripts, not by CI |
| `YOUTUBE_PRIVACY` (`private`) and the `YOUTUBE_*` secrets | `daily-short.yml` | upload step is skipped when `YOUTUBE_REFRESH_TOKEN` is unset; uploads stay private until the Google API audit passes | `gh secret list`; step `if:` on `HAS_YOUTUBE` |
| `TELEGRAM_BOT_TOKEN` | Actions secret | short delivery and failure message to chat `8851680837` | `gh secret list` |
| `CLAUDE_CODE_OAUTH_TOKEN` | Actions secret | blog job runs on plan usage, not API billing | `gh secret list`; a blog run that fails at auth |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `CLOUDFLARE_API_TOKEN` | Actions secrets | `newsletter.yml` Terraform credentials (`polymarket-tui-ci` user; Cloudflare token scoped to botsmith.dev DNS) | `gh secret list` |
| `blurb_model_id` | `infra/newsletter/variables.tf` | Bedrock model for the digest intro; empty disables the blurb | the variable's default; digest log |
| Workflow enabled or disabled | GitHub | whether a cron fires at all | `gh workflow list --all` (today: `daily-short.yml` is `disabled_manually`) |
| `POLYMARKET_EXECUTION_LIVE`, `L` toggle | the user's own machine (`~/.config/polymarket-tui/credentials.toml`) | real orders. Not a CI concern; documented in `docs/trading.md` | n/a here |

## Things that are risky to change

- Anything that would put Polymarket credentials into CI. There are none, by design: no
  `POLYMARKET_*` secret exists in this repo, recordings run `SHORTS_MODE=anon`, and every
  workflow other than `publish.yml` and `newsletter.yml` has `contents: read` or only what it
  needs. Adding a funder or private key to Actions would turn a content pipeline into a trading
  account. Do not.
- The release version. `publish.yml` ships whatever `pyproject.toml` says; forgetting the bump
  makes the run fail at upload (PyPI rejects the duplicate) and a tag that does not match the
  version confuses the tap. Bump, commit, tag, release, in that order (`docs/releasing.md`).
- The newsletter digest path. Any change to `handler_digest.py` or the schedule runs against
  real subscribers at 07:00 NZ with no retry and no staging environment. Test with the verified
  address only, and never invoke the Lambda twice for the same day.
- `newsletter.yml` and `infra/newsletter/backend.tf`. The state bucket has `prevent_destroy`;
  keep it. Applying locally breaks the audit trail the pipeline exists for.
- The `polymarket-tui-api.botsmith.dev` hostname and the Pages CNAME. Anything under
  `polymarket-tui.botsmith.dev` inherits github.io's CAA records and ACM cannot issue a
  certificate; the API host must stay a first-level name under the apex. The CNAME itself is
  owned by x402-services' Terraform.
- The blog job's self-merge condition. It is what keeps an automated PR from shipping code;
  widening the allowed diff removes the only review on a daily unattended write to `main`.
