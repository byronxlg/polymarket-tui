# --- SES: send digests from digest@polymarket-tui.botsmith.dev ---
# The identity domain also serves the landing page (a GitHub Pages CNAME,
# managed in x402-services' Terraform). None of the records below sit at that
# name itself, so the two configs never collide: DKIM lives under _domainkey.,
# the bounce domain under bounce., DMARC under _dmarc.
#
# NOTE: a fresh SES account is in sandbox mode - it can only send TO verified
# addresses. This account has production access, so no recipient identity is
# declared here: the sandbox test recipient was removed 2026-10-03 (the live
# identity had been gone since 2026-09-07 and the digest sent without it).

resource "aws_sesv2_email_identity" "domain" {
  email_identity = var.sender_domain
}

# Easy-DKIM: three CNAMEs prove domain ownership and sign outgoing mail.
resource "cloudflare_dns_record" "dkim" {
  count = 3

  zone_id = var.cloudflare_zone_id
  name    = "${aws_sesv2_email_identity.domain.dkim_signing_attributes[0].tokens[count.index]}._domainkey.${var.sender_domain}"
  type    = "CNAME"
  content = "${aws_sesv2_email_identity.domain.dkim_signing_attributes[0].tokens[count.index]}.dkim.amazonses.com"
  ttl     = 1
  proxied = false
}

# Custom MAIL FROM so SPF aligns with the sending domain.
resource "aws_sesv2_email_identity_mail_from_attributes" "domain" {
  email_identity         = aws_sesv2_email_identity.domain.email_identity
  mail_from_domain       = "bounce.${var.sender_domain}"
  behavior_on_mx_failure = "USE_DEFAULT_VALUE"
}

resource "cloudflare_dns_record" "mail_from_mx" {
  zone_id  = var.cloudflare_zone_id
  name     = "bounce.${var.sender_domain}"
  type     = "MX"
  content  = "feedback-smtp.${var.region}.amazonses.com"
  priority = 10
  ttl      = 1
  proxied  = false
}

resource "cloudflare_dns_record" "mail_from_spf" {
  zone_id = var.cloudflare_zone_id
  name    = "bounce.${var.sender_domain}"
  type    = "TXT"
  content = "\"v=spf1 include:amazonses.com ~all\""
  ttl     = 1
  proxied = false
}

resource "cloudflare_dns_record" "dmarc" {
  zone_id = var.cloudflare_zone_id
  name    = "_dmarc.${var.sender_domain}"
  type    = "TXT"
  content = "\"v=DMARC1; p=none;\""
  ttl     = 1
  proxied = false
}
