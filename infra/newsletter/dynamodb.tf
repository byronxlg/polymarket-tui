# One row per subscriber, keyed by normalized email. status walks
# pending -> confirmed -> unsubscribed; token gates confirm/unsubscribe links.
resource "aws_dynamodb_table" "subscribers" {
  name         = "${local.prefix}-subscribers"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "email"

  attribute {
    name = "email"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}
