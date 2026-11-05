# infra/newsletter

The newsletter is shut down (2026-11-05, Byron's request). The sign-up form, API, Lambdas,
schedule, SES identity and their DNS records were destroyed through this config. What is left
here is what outlives it:

- `polymarket-tui-newsletter-subscribers` (DynamoDB, `prevent_destroy`): kept because deleting
  data needs Byron's go. One row, Byron's own address. Nothing reads or writes it.
- `polymarket-tui-newsletter-3usd` and `-5usd` budgets: account-wide spend alerts to Byron, not
  specific to the newsletter. The directory name stays because the budget names, the state key
  and the workflow do.
- `polymarket-tui-tfstate` (S3, `prevent_destroy`): this config's remote state. Do not remove
  that lifecycle rule.
- `polymarket-tui-ci` (IAM user and policy): runs `.github/workflows/newsletter.yml`.

To bring the newsletter back: `git revert` the shutdown PRs (the code and how it worked are in
history at 5df0dd6), let `newsletter.yml` apply, and restore the form on `site/index.html`.

## Applying changes

Never apply locally. Push to main: `.github/workflows/newsletter.yml` runs `terraform plan -out`
and `apply` with the `polymarket-tui-ci` credentials (GitHub Actions secrets `AWS_ACCESS_KEY_ID`
and `AWS_SECRET_ACCESS_KEY`). Pull requests run plan only. Local `terraform plan` for inspection
is fine.

`polymarket-tui-ci` access keys are intentionally not in Terraform state. Create with:

```sh
doppler run --project global --config home -- aws iam create-access-key --user-name polymarket-tui-ci
```

then store as GitHub Actions repo secrets (`gh secret set`). Rotate by creating a second key,
updating the secrets, deleting the old one - never delete first.
