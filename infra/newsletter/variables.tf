variable "region" {
  type    = string
  default = "ap-southeast-2"
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone id for botsmith.dev"
  type        = string
  default     = "48ca6d98636690b501989633f07852a1"
}

variable "site_url" {
  description = "The landing page that hosts the signup form"
  type        = string
  default     = "https://polymarket-tui.botsmith.dev"
}

variable "api_domain" {
  description = "Public hostname for the signup/confirm/unsubscribe API. Must be a first-level name under the apex: a name under polymarket-tui.botsmith.dev inherits github.io's CAA records through the Pages CNAME during the tree-climb, and ACM cannot issue (CAA_ERROR, seen on the first deploy)."
  type        = string
  default     = "polymarket-tui-api.botsmith.dev"
}

variable "sender_domain" {
  description = "SES domain identity; digests are sent from digest@ this domain"
  type        = string
  default     = "polymarket-tui.botsmith.dev"
}

variable "test_recipient" {
  description = "Verified recipient for testing while SES is in sandbox mode; also receives budget alerts"
  type        = string
  default     = "byron.lg.smith@gmail.com"
}

variable "blurb_model_id" {
  description = "Bedrock model/inference-profile id for the digest intro blurb; empty disables it. claude-sonnet-5 is gated for this account on Bedrock (checked 2026-07-18: 'not available for this account'), so this is the newest invocable Sonnet - swap when access arrives."
  type        = string
  default     = "au.anthropic.claude-sonnet-4-6"
}
