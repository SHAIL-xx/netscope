variable "name" {
  description = "Name used for the ECS cluster and related resources."
  type        = string
  default     = "netscope"
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