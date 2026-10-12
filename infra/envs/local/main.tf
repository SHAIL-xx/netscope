module "netscope" {
  source = "../../modules/netscope"

  name = "netscope-local"

  tags = {
    Project     = "netscope"
    Environment = "local"
    ManagedBy   = "terraform"
  }
}
