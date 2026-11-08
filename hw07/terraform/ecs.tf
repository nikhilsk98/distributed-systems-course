resource "aws_ecs_cluster" "main" {
  name = "${var.name}-cluster"
  # Container Insights intentionally disabled (paid); default ECS metrics are enough.
  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.name}-order-api"
  retention_in_days = 1
}

resource "aws_cloudwatch_log_group" "processor" {
  name              = "/ecs/${var.name}-order-processor"
  retention_in_days = 1
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.name}-order-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = var.lab_role_arn
  task_role_arn            = var.lab_role_arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  container_definitions = jsonencode([{
    name         = "order-api"
    image        = "${aws_ecr_repository.repo["order-api"].repository_url}:${var.image_tag}"
    essential    = true
    portMappings = [{ containerPort = 8080, protocol = "tcp" }]
    environment = [
      { name = "SNS_TOPIC_ARN", value = aws_sns_topic.orders.arn },
      { name = "AWS_REGION", value = var.region },
      { name = "PAYMENT_CONCURRENCY", value = tostring(var.payment_concurrency) },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.api.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "api"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "processor" {
  family                   = "${var.name}-order-processor"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = var.lab_role_arn
  task_role_arn            = var.lab_role_arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  container_definitions = jsonencode([{
    name      = "order-processor"
    image     = "${aws_ecr_repository.repo["order-processor"].repository_url}:${var.image_tag}"
    essential = true
    environment = [
      { name = "SQS_QUEUE_URL", value = aws_sqs_queue.orders.url },
      { name = "AWS_REGION", value = var.region },
      { name = "WORKER_COUNT", value = tostring(var.worker_count) },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.processor.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "processor"
      }
    }
  }])
}

resource "aws_ecs_service" "api" {
  name                              = "order-api"
  cluster                           = aws_ecs_cluster.main.id
  task_definition                   = aws_ecs_task_definition.api.arn
  desired_count                     = 1
  launch_type                       = "FARGATE"
  health_check_grace_period_seconds = 30
  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "order-api"
    container_port   = 8080
  }
  depends_on = [aws_lb_listener.http, aws_route_table_association.private]
}

resource "aws_ecs_service" "processor" {
  name            = "order-processor"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.processor.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  # Stop the old task before starting the new one so two worker pools never overlap
  # during a worker-count change.
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100
  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }
  depends_on = [aws_route_table_association.private]
}
