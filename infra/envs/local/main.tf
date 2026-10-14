module "netscope" {
  source = "../../modules/netscope"

  name       = "netscope-local"
  vpc_id     = var.vpc_id
  subnet_ids = var.subnet_ids

  tags = {
    Project     = "netscope"
    Environment = "local"
    ManagedBy   = "terraform"
  }
}