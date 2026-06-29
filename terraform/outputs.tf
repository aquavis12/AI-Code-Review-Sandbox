output "api_url" {
  description = "API Gateway endpoint"
  value       = aws_apigatewayv2_stage.prod.invoke_url
}

output "frontend_url" {
  description = "CloudFront URL"
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "results_bucket" {
  description = "S3 bucket for review reports"
  value       = aws_s3_bucket.results.id
}

output "artifacts_bucket" {
  description = "S3 bucket for MicroVM build artifacts"
  value       = aws_s3_bucket.artifacts.id
}

output "microvm_build_role_arn" {
  description = "IAM role ARN for MicroVM image builds"
  value       = aws_iam_role.microvm_build_role.arn
}

output "frontend_bucket" {
  description = "S3 bucket for frontend files"
  value       = aws_s3_bucket.frontend.id
}
