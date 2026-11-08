variable "region" {
  type    = string
  default = "us-east-1"
}
variable "name" {
  type    = string
  default = "hw07"
}
variable "lab_role_arn" {
  type    = string
  default = "arn:aws:iam::719602427292:role/LabRole"
}
variable "image_tag" {
  type    = string
  default = "latest"
}
variable "worker_count" {
  description = "Goroutines in the SQS order processor"
  type        = number
  default     = 1
}
variable "payment_concurrency" {
  description = "Buffered-channel capacity of the simulated payment processor for /orders/sync"
  type        = number
  default     = 1
}
variable "enable_lambda" {
  description = "Create the Lambda function (Part III)"
  type        = bool
  default     = false
}
variable "enable_lambda_subscription" {
  description = "Subscribe the Lambda to SNS. Keep false during all Part II load tests."
  type        = bool
  default     = false
}
