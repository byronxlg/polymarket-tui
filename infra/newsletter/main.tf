data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  prefix     = "polymarket-tui-newsletter"
}

# --- Terraform state backend (bootstrapped locally once, see CLAUDE.md) ---

resource "aws_s3_bucket" "tfstate" {
  bucket = "polymarket-tui-tfstate"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# --- CI user: scoped Terraform plan/apply for GitHub Actions ---

resource "aws_iam_user" "ci" {
  name = "polymarket-tui-ci"
}

data "aws_iam_policy_document" "ci" {
  statement {
    sid       = "TerraformState"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.tfstate.arn, "${aws_s3_bucket.tfstate.arn}/*"]
  }

  statement {
    sid       = "ManageSubscriberTable"
    actions   = ["dynamodb:*"]
    resources = ["arn:aws:dynamodb:${var.region}:${local.account_id}:table/${local.prefix}-*"]
  }

  statement {
    sid       = "ManageBudgets"
    actions   = ["budgets:*"]
    resources = ["arn:aws:budgets::${local.account_id}:budget/polymarket-tui-*"]
  }

  statement {
    sid     = "ManageOwnIamSurface"
    actions = ["iam:*"]
    resources = [
      aws_iam_user.ci.arn,
      "arn:aws:iam::${local.account_id}:policy/polymarket-tui-ci",
    ]
  }
}

resource "aws_iam_policy" "ci" {
  name   = "polymarket-tui-ci"
  policy = data.aws_iam_policy_document.ci.json
}

resource "aws_iam_user_policy_attachment" "ci" {
  user       = aws_iam_user.ci.name
  policy_arn = aws_iam_policy.ci.arn
}

# IAM policy changes are eventually consistent; new grants used later in the
# same apply race the propagation (bit x402-services three times). Re-sleeps
# whenever the policy document changes; resources first created under a fresh
# grant should depend on this instead of the policy directly.
resource "time_sleep" "iam_propagation" {
  create_duration = "20s"
  triggers = {
    policy = aws_iam_policy.ci.policy
  }
}
