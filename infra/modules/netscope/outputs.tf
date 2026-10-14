output "cluster_name" {
  description = "Name of the ECS cluster."
  value       = aws_ecs_cluster.netscope.name
}

output "cluster_arn" {
  description = "ARN of the ECS cluster."
  value       = aws_ecs_cluster.netscope.arn
}

output "service_name" {
  description = "Name of the ECS service."
  value       = aws_ecs_service.netscope.name
}

output "task_definition_arn" {
  description = "ARN of the task definition the service runs."
  value       = aws_ecs_task_definition.netscope.arn
}

output "security_group_id" {
  description = "Security group attached to the container."
  value       = aws_security_group.netscope.id
}

output "log_group_name" {
  description = "CloudWatch log group the containers write to."
  value       = aws_cloudwatch_log_group.netscope.name
}