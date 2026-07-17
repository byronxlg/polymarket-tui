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
  description = "Verified recipient for testing while SES is in sandbox mode"
  type        = string
  default     = "byron.lg.smith@gmail.com"
}
