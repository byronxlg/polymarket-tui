# --- HTTP API: api.polymarket-tui.botsmith.dev -> Lambda ---
# The signup form on the landing page posts here; confirm/unsubscribe links in
# emails point here too. The hostname is fixed so the static site can hardcode it.

resource "aws_apigatewayv2_api" "api" {
  name          = "${local.prefix}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = [var.site_url]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["content-type"]
    max_age       = 86400
  }

  # The apigateway:* grant ships in this apply; order behind its propagation.
  depends_on = [time_sleep.iam_propagation]
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

# Explicit routes, deliberately no $default: a catch-all matches OPTIONS too,
# which routes browser CORS preflights to the lambda (404) instead of API
# Gateway's automatic preflight responder. With no route matching OPTIONS,
# the gateway answers preflights itself from cors_configuration.
resource "aws_apigatewayv2_route" "routes" {
  for_each = toset([
    "POST /subscribe",
    "GET /confirm",
    "GET /unsubscribe",
    "POST /unsubscribe",
  ])

  api_id    = aws_apigatewayv2_api.api.id
  route_key = each.value
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true

  # Abuse guard on a public unauthenticated endpoint.
  default_route_settings {
    throttling_rate_limit  = 5
    throttling_burst_limit = 20
  }
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

resource "aws_acm_certificate" "api" {
  domain_name       = var.api_domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [time_sleep.iam_propagation]
}

resource "cloudflare_dns_record" "acm_validation" {
  for_each = {
    for dvo in aws_acm_certificate.api.domain_validation_options : dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }

  zone_id = var.cloudflare_zone_id
  name    = trimsuffix(each.value.name, ".")
  type    = each.value.type
  content = trimsuffix(each.value.value, ".")
  ttl     = 60
  proxied = false
}

resource "aws_acm_certificate_validation" "api" {
  certificate_arn         = aws_acm_certificate.api.arn
  validation_record_fqdns = [for r in cloudflare_dns_record.acm_validation : r.name]
}

resource "aws_apigatewayv2_domain_name" "api" {
  domain_name = var.api_domain

  domain_name_configuration {
    certificate_arn = aws_acm_certificate_validation.api.certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }
}

resource "aws_apigatewayv2_api_mapping" "api" {
  api_id      = aws_apigatewayv2_api.api.id
  domain_name = aws_apigatewayv2_domain_name.api.id
  stage       = aws_apigatewayv2_stage.default.id
}

# DNS-only (not proxied) so TLS terminates at API Gateway with the ACM cert.
resource "cloudflare_dns_record" "api" {
  zone_id = var.cloudflare_zone_id
  name    = var.api_domain
  type    = "CNAME"
  content = aws_apigatewayv2_domain_name.api.domain_name_configuration[0].target_domain_name
  ttl     = 1
  proxied = false
}
