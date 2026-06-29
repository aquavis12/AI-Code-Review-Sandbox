# ==================================
# Lambda — Orchestrator Function
# ==================================

# Package the Lambda code
data "archive_file" "orchestrator_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src/orchestrator"
  output_path = "${path.module}/.build/orchestrator.zip"
}

# Lambda function
resource "aws_lambda_function" "orchestrator" {
  function_name    = "${var.project_name}-orchestrator"
  filename         = data.archive_file.orchestrator_zip.output_path
  source_code_hash = data.archive_file.orchestrator_zip.output_base64sha256
  handler          = "app.handler"
  runtime          = "python3.11"
  timeout          = 120
  memory_size      = 512
  role             = aws_iam_role.lambda_role.arn

  environment {
    variables = {
      MICROVM_IMAGE_NAME = var.microvm_image_name
      BEDROCK_MODEL_ID   = var.bedrock_model_id
      RESULTS_BUCKET     = aws_s3_bucket.results.id
      AWS_REGION_NAME    = var.region
    }
  }

  depends_on = [aws_iam_role_policy_attachment.lambda_basic]
}
