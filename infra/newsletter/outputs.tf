output "ci_user" {
  value = aws_iam_user.ci.name
}

output "subscribers_table" {
  value = aws_dynamodb_table.subscribers.name
}
