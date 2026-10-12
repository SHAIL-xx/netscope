resource "aws_cloudwatch_log_group" "netscope" {
  name              = "/ecs/${var.name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_ecs_cluster" "netscope" {
  name = var.name
  tags = var.tags
}