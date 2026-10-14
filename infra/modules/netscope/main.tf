data "aws_region" "current" {}

resource "aws_cloudwatch_log_group" "netscope" {
  name              = "/ecs/${var.name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_ecs_cluster" "netscope" {
  name = var.name
  tags = var.tags
}

# --- IAM: the role ECS uses to start the container and write its logs -------

data "aws_iam_policy_document" "ecs_tasks_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "write_logs" {
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.netscope.arn}:*"]
  }
}

resource "aws_iam_role" "task_execution" {
  name               = "${var.name}-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "write_logs" {
  name   = "write-logs"
  role   = aws_iam_role.task_execution.id
  policy = data.aws_iam_policy_document.write_logs.json
}

# --- Network: who can reach the container ----------------------------------

resource "aws_security_group" "netscope" {
  name        = "${var.name}-sg"
  description = "Dashboard access for ${var.name}"
  vpc_id      = var.vpc_id

  ingress {
    description = "netscope dashboard and metrics"
    from_port   = var.container_port
    to_port     = var.container_port
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  egress {
    description = "All outbound traffic (checking the sites, pulling the image)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.tags
}

# --- ECS: what to run and how many copies -----------------------------------

resource "aws_ecs_task_definition" "netscope" {
  family                   = var.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.cpu)
  memory                   = tostring(var.memory)
  execution_role_arn       = aws_iam_role.task_execution.arn

  container_definitions = jsonencode([
    {
      name      = "netscope"
      image     = var.image
      essential = true

      portMappings = [
        { containerPort = var.container_port, protocol = "tcp" }
      ]

      environment = [
        { name = "NETSCOPE_TARGETS", value = join(",", var.targets) },
        { name = "NETSCOPE_INTERVAL", value = tostring(var.interval_seconds) },
      ]

      readonlyRootFilesystem = true

      healthCheck = {
        command     = ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${var.container_port}/healthz', timeout=2)"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 10
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.netscope.name
          "awslogs-region"        = data.aws_region.current.region
          "awslogs-stream-prefix" = "netscope"
        }
      }
    }
  ])

  tags = var.tags
}

resource "aws_ecs_service" "netscope" {
  name            = var.name
  cluster         = aws_ecs_cluster.netscope.id
  task_definition = aws_ecs_task_definition.netscope.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.netscope.id]
    assign_public_ip = var.assign_public_ip
  }

  # The role must be allowed to write logs before the first task starts.
  depends_on = [aws_iam_role_policy.write_logs]

  tags = var.tags
}