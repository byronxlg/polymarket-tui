terraform {
  backend "s3" {
    bucket       = "polymarket-tui-tfstate"
    key          = "newsletter/terraform.tfstate"
    region       = "ap-southeast-2"
    use_lockfile = true
  }
}
