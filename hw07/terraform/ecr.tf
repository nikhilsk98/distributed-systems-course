locals {
  repos = ["order-api", "order-processor"]
}

resource "aws_ecr_repository" "repo" {
  for_each             = toset(local.repos)
  name                 = "${var.name}-${each.key}"
  force_delete         = true
  image_tag_mutability = "MUTABLE"
}

resource "aws_ecr_lifecycle_policy" "keep3" {
  for_each   = aws_ecr_repository.repo
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the last 3 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 3
      }
      action = { type = "expire" }
    }]
  })
}
