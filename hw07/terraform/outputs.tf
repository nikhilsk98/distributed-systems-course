output "alb_url" { value = "http://${aws_lb.api.dns_name}" }
output "alb_arn_suffix" { value = aws_lb.api.arn_suffix }
output "sns_topic_arn" { value = aws_sns_topic.orders.arn }
output "sqs_queue_url" { value = aws_sqs_queue.orders.url }
output "ecs_cluster" { value = aws_ecs_cluster.main.name }
output "ecr_api_url" { value = aws_ecr_repository.repo["order-api"].repository_url }
output "ecr_processor_url" { value = aws_ecr_repository.repo["order-processor"].repository_url }
output "lambda_name" { value = var.enable_lambda ? aws_lambda_function.orders[0].function_name : "" }
