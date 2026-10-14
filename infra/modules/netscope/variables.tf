variable "name" {
  description = "Name used for the ECS cluster and related resources."
  type        = string
  default     = "netscope"
}

variable "image" {
  description = "Container image to run."
  type        = string
  default     = "ghcr.io/shail-xx/netscope:0.1.1"
}

variable "targets" {
  description = "Websites netscope should check."
  type        = list(string)
  default     = ["github.com", "example.com"]
}

variable "interval_seconds" {
  description = "Seconds between checks."
  type        = number
  default     = 10
}

variable "container_port" {
  description = "Port netscope listens on inside the container."
  type        = number
  default     = 8000
}

variable "cpu" {
  description = "Fargate CPU units (256 = 0.25 vCPU)."
  type        = number
  default     = 256
}

variable "memory" {
  description = "Fargate memory in MiB."
  type        = number
  default     = 512
}

variable "desired_count" {
  description = "How many copies of the container to keep running."
  type        = number
  default     = 1
}

variable "vpc_id" {
  description = "VPC the security group is created in."
  type        = string
}

variable "subnet_ids" {
  description = "Subnets the container may run in."
  type        = list(string)
}

variable "assign_public_ip" {
  description = "Give the container a public IP so it can reach the internet (pull the image, check sites)."
  type        = bool
  default     = true
}

variable "allowed_cidr_blocks" {
  description = "Who may reach the dashboard. On real AWS use your own address, for example 203.0.113.7/32."
  type        = list(string)
  default     = ["127.0.0.1/32"]

  validation {
    condition     = alltrue([for c in var.allowed_cidr_blocks : can(cidrhost(c, 0))])
    error_message = "Every entry must be a valid CIDR block such as 203.0.113.7/32."
  }
}

variable "log_retention_days" {
  description = "How many days CloudWatch keeps the container logs."
  type        = number
  default     = 7
}

variable "tags" {
  description = "Tags added to every resource."
  type        = map(string)
  default     = {}
}