# Kept when the newsletter was shut down (2026-11-05): nothing reads or writes it,
# and deleting it needs Byron's go. One row, Byron's own address.
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

  lifecycle {
    prevent_destroy = true
  }
}
