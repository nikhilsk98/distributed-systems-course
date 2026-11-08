# Part III. The binary is built by scripts/build_lambda.sh (GOOS=linux GOARCH=amd64).
data "archive_file" "lambda" {
  count       = var.enable_lambda ? 1 : 0
  type        = "zip"
  source_file = "${path.module}/../lambda/build/bootstrap"
  output_path = "${path.module}/../lambda/build/lambda.zip"
}

resource "aws_cloudwatch_log_group" "lambda" {
  count             = var.enable_lambda ? 1 : 0
  name              = "/aws/lambda/${var.name}-order-lambda"
  retention_in_days = 1
}

resource "aws_lambda_function" "orders" {
  count            = var.enable_lambda ? 1 : 0
  function_name    = "${var.name}-order-lambda"
  role             = var.lab_role_arn
  runtime          = "provided.al2"
  handler          = "bootstrap"
  architectures    = ["x86_64"]
  memory_size      = 512
  timeout          = 10
  filename         = data.archive_file.lambda[0].output_path
  source_code_hash = data.archive_file.lambda[0].output_base64sha256
  depends_on       = [aws_cloudwatch_log_group.lambda]
}

resource "aws_lambda_permission" "sns" {
  count         = var.enable_lambda ? 1 : 0
  statement_id  = "AllowSNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.orders[0].function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.orders.arn
}

# Disabled by default. Only enabled for the Part III curl test (never during load tests).
resource "aws_sns_topic_subscription" "lambda" {
  count     = var.enable_lambda && var.enable_lambda_subscription ? 1 : 0
  topic_arn = aws_sns_topic.orders.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.orders[0].arn
}
