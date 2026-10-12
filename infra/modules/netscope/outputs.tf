output "cluster_name" {
  description = "Name of the ECS cluster."
  value       = aws_ecs_cluster.netscope.name
}

output "cluster_arn" {
  description = "ARN of the ECS cluster."
  value       = aws_ecs_cluster.netscope.arn
}

output "log_group_name" {
  description = "CloudWatch log group the containers write to."
  value       = aws_cloudwatch_log_group.netscope.name
}