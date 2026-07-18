# Spend alerts (user request 2026-07-18): email at $3 and $5 of monthly spend.
# Account-wide by design: the account's non-newsletter baseline is ~$0.12/month
# (checked 2026-07-18), so these are effectively project alerts without the
# cost-allocation-tag activation lag (tags only apply to usage recorded after
# activation, and none are active in this account).

resource "aws_budgets_budget" "monthly" {
  for_each = {
    "polymarket-tui-newsletter-3usd" = "3.0"
    "polymarket-tui-newsletter-5usd" = "5.0"
  }

  name         = each.key
  budget_type  = "COST"
  limit_amount = each.value
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.test_recipient]
  }
}
