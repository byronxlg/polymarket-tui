data "aws_caller_identity" "current" {}

locals {
  account_id   = data.aws_caller_identity.current.account_id
  prefix       = "polymarket-tui-newsletter"
  sender_email = "digest@${var.sender_domain}"
  api_base_url = "https://${var.api_domain}"
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
    sid     = "ManageLambda"
    actions = ["lambda:*"]
    resources = [
      "arn:aws:lambda:${var.region}:${local.account_id}:function:${local.prefix}-*",
      "arn:aws:lambda:${var.region}:${local.account_id}:function:${local.prefix}-*:*",
    ]
  }

  statement {
    sid       = "ManageLogs"
    actions   = ["logs:*"]
    resources = ["arn:aws:logs:${var.region}:${local.account_id}:log-group:/aws/lambda/${local.prefix}*"]
  }

  # List-type action; IAM does not support resource-scoping it.
  statement {
    sid       = "DescribeLogGroups"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["*"]
  }

  statement {
    sid       = "ManageSubscriberTable"
    actions   = ["dynamodb:*"]
    resources = ["arn:aws:dynamodb:${var.region}:${local.account_id}:table/${local.prefix}-*"]
  }

  # SES identities. List/Get calls are not resource-scopable.
  statement {
    sid       = "ManageSesIdentities"
    actions   = ["ses:*"]
    resources = ["arn:aws:ses:${var.region}:${local.account_id}:identity/*"]
  }

  statement {
    sid       = "ReadSesAccount"
    actions   = ["ses:Get*", "ses:List*", "ses:Describe*"]
    resources = ["*"]
  }

  # ACM create/list actions are not resource-scopable.
  statement {
    sid       = "ManageCertificates"
    actions   = ["acm:*"]
    resources = ["*"]
  }

  # API Gateway ARNs carry no account id and the v2 API id is generated, so
  # scope by region only.
  statement {
    sid       = "ManageApiGateway"
    actions   = ["apigateway:*"]
    resources = ["arn:aws:apigateway:${var.region}::/*"]
  }

  statement {
    sid     = "ManageSchedules"
    actions = ["scheduler:*"]
    resources = [
      "arn:aws:scheduler:${var.region}:${local.account_id}:schedule/default/${local.prefix}-*",
    ]
  }

  statement {
    sid       = "ListSchedules"
    actions   = ["scheduler:ListSchedules", "scheduler:ListScheduleGroups", "scheduler:GetScheduleGroup"]
    resources = ["*"]
  }

  statement {
    sid     = "ManageOwnIamSurface"
    actions = ["iam:*"]
    resources = [
      aws_iam_user.ci.arn,
      "arn:aws:iam::${local.account_id}:policy/polymarket-tui-ci",
      "arn:aws:iam::${local.account_id}:role/${local.prefix}-*",
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
