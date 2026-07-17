output "api_url" {
  value = local.api_base_url
}

output "sender_email" {
  value = local.sender_email
}

output "ci_user" {
  value = aws_iam_user.ci.name
}

output "subscribers_table" {
  value = aws_dynamodb_table.subscribers.name
}
