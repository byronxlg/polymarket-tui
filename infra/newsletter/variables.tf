variable "region" {
  type    = string
  default = "ap-southeast-2"
}

variable "test_recipient" {
  description = "Receives the budget alerts"
  type        = string
  default     = "byron.lg.smith@gmail.com"
}
