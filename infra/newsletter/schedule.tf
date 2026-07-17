# Daily digest at 07:00 New Zealand time (EventBridge Scheduler handles DST).
# No retries: retrying a partially-sent digest would double-send it.

resource "aws_iam_role" "scheduler" {
  name = "${local.prefix}-scheduler"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "scheduler" {
  name = "invoke-digest"
  role = aws_iam_role.scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.digest.arn
    }]
  })
}

resource "aws_scheduler_schedule" "digest" {
  name = "${local.prefix}-digest"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "cron(0 7 * * ? *)"
  schedule_expression_timezone = "Pacific/Auckland"

  target {
    arn      = aws_lambda_function.digest.arn
    role_arn = aws_iam_role.scheduler.arn

    retry_policy {
      maximum_retry_attempts = 0
    }
  }

  depends_on = [time_sleep.iam_propagation]
}
