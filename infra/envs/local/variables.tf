variable "emulator_endpoint" {
  description = "Where the local AWS emulator (Floci) listens."
  type        = string
  default     = "http://localhost:4566"
}

variable "vpc_id" {
  description = "Default VPC that Floci creates (see: aws ec2 describe-vpcs)."
  type        = string
  default     = "vpc-default-us-east-1"
}

variable "subnet_ids" {
  description = "Default subnets that Floci creates (see: aws ec2 describe-subnets)."
  type        = list(string)
  default = [
    "subnet-default-us-east-1-a",
    "subnet-default-us-east-1-b",
    "subnet-default-us-east-1-c",
  ]
}