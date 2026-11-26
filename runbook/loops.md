---
project: polymarket-tui
reviewed: 2026-11-21
loops: [L-blog]
kill_switch: "gh workflow disable blog-post.yml -R byronxlg/polymarket-tui (not yet exercised; the cron is already off)"
---

# Agent loops

One loop: `.github/workflows/blog-post.yml` runs `anthropics/claude-code-action@v1` on manual
dispatch only. The daily cron (`23 6 * * *`) was stopped 2026-10-03 at Byron's request and sits
commented in the workflow header; the last run was 2026-10-02. The model is not pinned; that run
reported `claude-sonnet-5-5`, billed to Byron's plan through `CLAUDE_CODE_OAUTH_TOKEN`. It
follows `.claude/skills/blog-post/SKILL.md`: finds a story from news (WebSearch, WebFetch) and
the public Polymarket APIs (`curl`), writes a static HTML post, opens a PR and merges it itself.
No loop here trades: the app's wallet keys are never in this repo or its secrets. The one thing
that must never happen: the loop releases the package to PyPI or reaches the AWS and Cloudflare
keys held as repo secrets. Today only the prompt and token limits stand in the way; see Guards.
Method and scales: management `docs/standard.md` "Agent loops".

## Loop cards

### L-blog blog post

| Field | Value |
| --- | --- |
| Purpose | Write and ship one blog post to https://polymarket-tui.botsmith.dev/blog/ |
| Trigger | `workflow_dispatch` only (`gh workflow run blog-post.yml`); cron removed 2026-10-03 |
| Inputs | `.claude/skills/blog-post/SKILL.md`, the prompt in `blog-post.yml`, `docs/blog-todo.md`, `docs/trading.md`, `docs/api-reference.md`, live Gamma, CLOB and Data API responses, and any web page it fetches: untrusted input |
| Outputs | branch `blog/<slug>`, a PR, a squash-merge to `main`, a `gh workflow run pages.yml` deploy to GitHub Pages |
| Done when | a post-only PR is merged and `pages.yml` dispatched, or an open `blog/` PR exists and the run says why it stopped |
| Checked by | nothing outside the model. No verify step in the job; `ci.yml` does not run on PRs made with `GITHUB_TOKEN`; no failure notification (runbook README) |
| Not done if | a pushed `blog/` branch with no PR; the new slug missing from `site/blog/index.html`, `site/index.html`, `site/blog/feed.xml` or `site/sitemap.xml`; a merged diff outside `site/blog/*`, the landing `#blog` list, `site/sitemap.xml`, `docs/blog-todo.md` |
| Caps | `--max-turns 80` (`claude_args`, enforced by the CLI; the action has no turn input); `timeout-minutes: 30` on the job (past runs 3 to 7 min, 25 turns); no spend cap (plan usage); `concurrency: blog-post` |
| On cap | the action reports success with nothing shipped; nobody is told |
| Stop | trigger is manual, so not dispatching is the stop; `gh workflow disable blog-post.yml -R byronxlg/polymarket-tui` blocks dispatch; `gh run cancel <id>` for one run |
| Credentials | `CLAUDE_CODE_OAUTH_TOKEN` (Byron's Claude plan); `GITHUB_TOKEN` as `GH_TOKEN` and the checkout credential, with `contents: write`, `pull-requests: write`, `actions: write`, `id-token: write`. Not in its env but in the repo: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `CLOUDFLARE_API_TOKEN`, `TELEGRAM_BOT_TOKEN`, `YOUTUBE_*` |
| Memory and log | git: `docs/blog-todo.md` Shipped list, PRs and merge commits; run logs and result JSON in Actions for 90 days |
| Highest grade | G3 reachable (PyPI release), held only by the prompt (O1); see Actions |
| Known failure modes | none recorded |

## Actions

| Loop | Action | Grade | Oversight | Enforced by | Why this pairing |
| --- | --- | --- | --- | --- | --- |
| L-blog | read repo, WebSearch, WebFetch, `curl` the public Polymarket APIs | G0 | O1 | run log | no keys for the APIs; reads only |
| L-blog | write files, run `pricechart.py`, serve the site locally | G1 | O1 | ephemeral runner | thrown away at job end |
| L-blog | push a `blog/` branch, open a PR | G1 | O2 | PR visible | close to undo |
| L-blog | squash-merge a post-only PR to `main` | G2 | O2 | prompt only | Byron authorized post-only merges 2026-07-17; revert is the undo. No code checks the diff |
| L-blog | dispatch `pages.yml` (public site deploy) | G2 | O2 | prompt only | static site; revert plus redeploy |
| L-blog | person dispatches the run | G2 | O3 | `workflow_dispatch` only | a person starts every run, but does not see the post before it is live |
| L-blog | push any file straight to `main` (main is unprotected) | G2 | O1 | tool list only (`git push` allowed to `blog/` branches; `python3` could still do it); `GITHUB_TOKEN` cannot change `.github/workflows/*`, and its pushes do not trigger `newsletter.yml` (no dispatch) or `publish.yml` | revert is the undo; should be O6 |
| L-blog | bump `pyproject.toml` on `main`, then `gh workflow run publish.yml` (PyPI release; environment `pypi` has no protection rules) | G3 | O1 | tool list only (`gh workflow run` allowed for `pages.yml` alone; `python3` or `curl` with the token could still do it); `actions: write` allows the dispatch | a PyPI release reaches `pip install` and, within a day, Homebrew; should be O6 |
| L-blog | send data out (HTTP to any host) | G3 | O1 | nothing; Bash and network unrestricted | public repo; the exposure is the run's tokens |
| L-blog | read AWS, Cloudflare, Telegram, YouTube secrets | G3 | O6 | not in the step's env; `GITHUB_TOKEN` cannot add a workflow that would expose them | hard block holds as long as workflow files stay out of the token's reach |

## Guards

- [x] Done condition written before the run: in the prompt and the skill (section 6).
- [ ] Checker independent of the loop: no. The job has no verify step (skillfold's
      `blog-post.yml` has one to copy), no failure notification, and `ci.yml` does not run.
- [ ] Tools are an allow-list: partly (2026-11-26). `Bash` is scoped to `curl`, `jq`, `python3`,
      a few read-only shell commands, `git` on a `blog/` branch, `gh pr` and
      `gh workflow run pages.yml`. `gh release`, `gh workflow run publish.yml` and `git push` to
      `main` are no longer on the list, but `curl` and `python3` can still reach any host or run
      any code with the token, so this narrows the tool list and is not a block. Not yet proven
      by a run: the first manual dispatch should be read for permission denials.
- [ ] Keys scoped: no. `GITHUB_TOKEN` holds `contents: write` and `actions: write` on an
      unprotected `main`; the OAuth token is Byron's plan token.
- [x] Works in an isolated place: an ephemeral Actions runner, a fresh checkout per run.
- [ ] Turn, time and spend caps outside the model: turns yes (80); time yes
      (`timeout-minutes: 30`); no spend cap.
- [x] Stops itself when it makes no progress: manual trigger only, so there is no retry loop.
- [ ] Kill switch tested: `gh workflow disable` not exercised.
- [x] Undo for each G2 action: revert commit, close PR, redeploy.
- [ ] Every G2 and G3 action has a person or a hard block: no. The PyPI release row is held
      only by the prompt.
- [ ] Log of every run kept: partly. Actions keeps logs 90 days; memory in git.

The real risk: the loop reads news pages and search results with `Bash` and `WebFetch` while it
holds a write token on an unprotected `main` and `actions: write`. A prompt injection in a
fetched page could push to `main` or bump the version and dispatch `publish.yml`, which uploads
to PyPI through an unprotected environment.

Recommended hardening before the cron is ever turned back on (item 6 is done; 1 to 5 are open):

1. Add a "Verify the run shipped something" step like skillfold's, and a Telegram failure step
   like `daily-short.yml`'s.
2. Protect `main` (require a PR and the `ci.yml` checks).
3. Drop `actions: write`; dispatch `pages.yml` from a separate job after the agent step.
4. Move the merge out of the model: a shell step merges only if `git diff --name-only` is
   inside the post's sync files.
5. Add a required reviewer to the `pypi` environment, or remove `publish.yml`'s
   `workflow_dispatch`.
6. Done 2026-11-26: `Bash` scoped, `timeout-minutes: 30`, turns 150 to 80. Read the first
   manual run for permission denials and widen only what the skill needs.

## Signals

| Signal | Recorded in | Acts when | health.md |
| --- | --- | --- | --- |
| Turns and wall time against cap | result JSON in the Actions log (`num_turns`; 25 on 2026-10-02), job duration | not acted on | none (tier 3) |
| Spend against cap, cost per finished item | result JSON `total_cost_usd` ($0.63 on 2026-10-02) | not acted on | none |
| Stop reason and outcome | result `subtype`; the run's final message | not acted on: no verify step | none |
| No-progress streak | not recorded | | none |
| Grade mix (G0 to G3 counts) | not recorded | | none |
| Gates hit and refusals | result `permission_denials_count` | not acted on | none |
