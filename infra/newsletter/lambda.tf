# Both functions ship in one zip of src/; they differ only in handler entrypoint.
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/src"
  output_path = "${path.module}/build/lambda.zip"
  excludes    = ["__pycache__"]
}

# --- API lambda: subscribe / confirm / unsubscribe ---

resource "aws_iam_role" "api" {
  name = "${local.prefix}-api"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "api_logs" {
  role       = aws_iam_role.api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "api" {
  name = "subscribers-and-send"
  role = aws_iam_role.api.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.subscribers.arn
      },
      {
        Effect   = "Allow"
        Action   = ["ses:SendEmail", "ses:SendRawEmail"]
        Resource = "arn:aws:ses:${var.region}:${local.account_id}:identity/*"
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.prefix}-api"
  retention_in_days = 30
}

resource "aws_lambda_function" "api" {
  function_name    = "${local.prefix}-api"
  role             = aws_iam_role.api.arn
  runtime          = "python3.12"
  handler          = "handler_api.lambda_handler"
  architectures    = ["arm64"]
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  memory_size      = 256
  timeout          = 15

  # Cost guardrail: caps concurrent executions (and therefore worst-case spend).
  reserved_concurrent_executions = 10

  environment {
    variables = {
      TABLE_NAME   = aws_dynamodb_table.subscribers.name
      SENDER_EMAIL = local.sender_email
      API_BASE_URL = local.api_base_url
      SITE_URL     = var.site_url
    }
  }

  depends_on = [aws_cloudwatch_log_group.api, time_sleep.iam_propagation]
}

# --- Digest lambda: build and send the daily email ---

resource "aws_iam_role" "digest" {
  name = "${local.prefix}-digest"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "digest_logs" {
  role       = aws_iam_role.digest.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "digest" {
  name = "subscribers-and-send"
  role = aws_iam_role.digest.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:Scan"]
        Resource = aws_dynamodb_table.subscribers.arn
      },
      {
        Effect   = "Allow"
        Action   = ["ses:SendEmail", "ses:SendRawEmail"]
        Resource = "arn:aws:ses:${var.region}:${local.account_id}:identity/*"
      },
      # Blurb generation. Invoking a cross-region inference profile needs the
      # profile ARN plus the foundation model in every destination region.
      {
        Effect = "Allow"
        Action = ["bedrock:InvokeModel"]
        Resource = [
          "arn:aws:bedrock:${var.region}:${local.account_id}:inference-profile/${var.blurb_model_id}",
          "arn:aws:bedrock:*::foundation-model/anthropic.*",
        ]
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "digest" {
  name              = "/aws/lambda/${local.prefix}-digest"
  retention_in_days = 30
}

resource "aws_lambda_function" "digest" {
  function_name    = "${local.prefix}-digest"
  role             = aws_iam_role.digest.arn
  runtime          = "python3.12"
  handler          = "handler_digest.lambda_handler"
  architectures    = ["arm64"]
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  memory_size      = 256
  timeout          = 300

  reserved_concurrent_executions = 1

  environment {
    variables = {
      TABLE_NAME     = aws_dynamodb_table.subscribers.name
      SENDER_EMAIL   = local.sender_email
      API_BASE_URL   = local.api_base_url
      SITE_URL       = var.site_url
      BLURB_MODEL_ID = var.blurb_model_id
    }
  }

  depends_on = [aws_cloudwatch_log_group.digest, time_sleep.iam_propagation]
}

# A partially-sent digest must never re-run automatically (some subscribers
# would get the email twice) - same principle as the app's never-auto-retry
# rule for timed-out orders.
resource "aws_lambda_function_event_invoke_config" "digest" {
  function_name          = aws_lambda_function.digest.function_name
  maximum_retry_attempts = 0
}
