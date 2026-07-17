# infra/newsletter

Terraform for the daily digest newsletter: subscribers sign up on the landing
page, confirm by email (double opt-in), and get one email a day with Polymarket
movers, volume leaders, ending-soon markets, and new markets. Region:
ap-southeast-2. Costs sit inside the Lambda/DynamoDB free tiers at current
scale; both functions carry reserved-concurrency caps.

## Pieces

- `polymarket-tui-newsletter-api` (python3.12/arm64): POST /subscribe,
  GET /confirm, GET|POST /unsubscribe, behind an HTTP API at
  `polymarket-tui-api.botsmith.dev` (ACM cert, Cloudflare DNS, throttled).
  The signup form in `site/index.html` posts here and hardcodes the hostname.
  The hostname must stay a first-level name under the apex: anything under
  `polymarket-tui.botsmith.dev` inherits github.io's CAA records through the
  Pages CNAME during the CA's tree-climb, and ACM cannot issue a cert
  (CAA_ERROR - hit on the first deploy with `api.polymarket-tui.`).
- `polymarket-tui-newsletter-digest` (python3.12/arm64): builds the digest
  from Gamma and sends via SES. EventBridge Scheduler fires it daily at 07:00
  Pacific/Auckland. Retries are disabled at both the schedule and the lambda
  (`maximum_retry_attempts = 0`): retrying a partially-sent digest would
  double-send it - same principle as the app's timed-out-order rule.
- `polymarket-tui-newsletter-subscribers` (DynamoDB): one row per email;
  status walks pending -> confirmed -> unsubscribed; a per-subscriber token
  gates confirm/unsubscribe links.
- SES identity `polymarket-tui.botsmith.dev`, sender
  `digest@polymarket-tui.botsmith.dev`, DKIM + custom MAIL FROM
  (`bounce.`) + DMARC records in Cloudflare.

Lambda code lives in `src/` and ships as an `archive_file` zip inside this
config - app-code pushes redeploy through the same plan/apply pipeline, no
separate code-deploy path. The modules that don't touch AWS (`digest_data`,
`digest_render`, `nl_common`) are stdlib-only and unit-tested by
`tests/test_newsletter_digest.py` in the repo's normal pytest run.

## DNS ownership note

The botsmith.dev zone also carries the landing-page Pages CNAME
(`polymarket-tui.botsmith.dev`), which is managed in x402-services' Terraform,
not here. This config only manages newsletter-specific record names (DKIM
under `_domainkey.`, `bounce.`, `_dmarc.`, `polymarket-tui-api.`), so the two states never
touch the same records.

## State

Remote state in S3 (`s3://polymarket-tui-tfstate/newsletter/terraform.tfstate`)
with S3 native locking (`use_lockfile`, no DynamoDB). The state bucket is
managed here with `prevent_destroy` - do not remove that lifecycle rule.

## Applying changes

Never apply locally. Push to main: `.github/workflows/newsletter.yml` runs
`terraform plan -out` + `apply` with the `polymarket-tui-ci` credentials
(GitHub Actions secrets `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`) and a
Cloudflare token scoped to botsmith.dev DNS (`CLOUDFLARE_API_TOKEN`). Pull
requests run plan only. Local `terraform plan` for inspection is fine.

### Bootstrap (one-time, NOT yet done)

The state bucket and CI user cannot create themselves. Same procedure as
x402-services: comment out `backend.tf`, `terraform apply -target` of the
tfstate bucket resources + `polymarket-tui-ci` user/policy/attachment with
local state under admin credentials, restore `backend.tf`, then
`terraform init -migrate-state`. Everything else (lambdas, SES, API, DNS,
schedule) is first applied by GitHub Actions.

### CI credentials (out-of-band, documented exception)

`polymarket-tui-ci` access keys are intentionally not in Terraform state.
Create with:

```sh
doppler run --project global --config home -- aws iam create-access-key --user-name polymarket-tui-ci
```

then store as GitHub Actions repo secrets (`gh secret set`). Rotate by
creating a second key, updating the secrets, deleting the old one - never
delete first.

## SES sandbox

A fresh SES account only delivers to verified addresses. The config verifies
`byron.lg.smith@gmail.com` as a test recipient (a verification email arrives
on first apply and must be clicked). Before real subscribers can receive
anything, request production access once in the SES console
(ap-southeast-2 -> Account dashboard -> Request production access; cite the
double-opt-in flow and the one-click unsubscribe headers). Until then,
subscribe confirmations to unverified addresses fail silently server-side by
design (the API never leaks delivery state).

## Testing a real run

Invoking the digest lambda sends real email to every confirmed subscriber -
treat it like the money path. To exercise it end to end while in sandbox:
subscribe with the verified test address on the site, click the confirm link,
then invoke `polymarket-tui-newsletter-digest` from the Lambda console (or
wait for the 07:00 NZ run). Read the CloudWatch summary line
(`sent/failed/subscribers`) rather than assuming.

## Follow-ups not built yet

- Bounce/complaint handling (SES event destination -> suppress subscriber).
  Matters once the list is bigger than friends-and-family.
- A welcome email on confirm (today the confirm page is the only feedback).
