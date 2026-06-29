# ==================================
# IAM — Lambda Execution Role
# ==================================

resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Basic Lambda execution (CloudWatch Logs)
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Lambda MicroVMs permissions
resource "aws_iam_role_policy" "microvm_policy" {
  name = "${var.project_name}-microvm"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda-microvms:RunMicrovm",
          "lambda-microvms:GetMicrovm",
          "lambda-microvms:TerminateMicrovm",
          "lambda-microvms:CreateMicrovmAuthToken"
        ]
        Resource = "*"
      }
    ]
  })
}

# Bedrock permissions
resource "aws_iam_role_policy" "bedrock_policy" {
  name = "${var.project_name}-bedrock"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = "*"
      }
    ]
  })
}

# S3 access for results bucket
resource "aws_iam_role_policy" "s3_policy" {
  name = "${var.project_name}-s3"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.results.arn}/*"
      }
    ]
  })
}

# ==================================
# IAM — MicroVM Build Role (for image creation)
# ==================================

resource "aws_iam_role" "microvm_build_role" {
  name = "${var.project_name}-microvm-build"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = ["sts:AssumeRole", "sts:TagSession"]
    }]
  })
}

resource "aws_iam_role_policy" "microvm_build_policy" {
  name = "${var.project_name}-microvm-build"
  role = aws_iam_role.microvm_build_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.artifacts.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}
