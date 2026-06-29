# ==================================
# API Gateway — REST API
# ==================================

resource "aws_apigatewayv2_api" "review_api" {
  name          = "${var.project_name}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_headers = ["Content-Type", "Authorization", "X-Requested-With"]
    allow_methods = ["POST", "GET", "OPTIONS"]
    allow_origins = ["*"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_stage" "prod" {
  api_id      = aws_apigatewayv2_api.review_api.id
  name        = "prod"
  auto_deploy = true
}

# Lambda integration
resource "aws_apigatewayv2_integration" "lambda_integration" {
  api_id                 = aws_apigatewayv2_api.review_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.orchestrator.invoke_arn
  payload_format_version = "2.0"
}

# POST /review
resource "aws_apigatewayv2_route" "post_review" {
  api_id    = aws_apigatewayv2_api.review_api.id
  route_key = "POST /review"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
}

# POST /scan (new unified endpoint)
resource "aws_apigatewayv2_route" "post_scan" {
  api_id    = aws_apigatewayv2_api.review_api.id
  route_key = "POST /scan"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
}

# GET /review/{review_id}
resource "aws_apigatewayv2_route" "get_review" {
  api_id    = aws_apigatewayv2_api.review_api.id
  route_key = "GET /review/{review_id}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_integration.id}"
}

# Permission for API Gateway to invoke Lambda
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.orchestrator.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.review_api.execution_arn}/*/*"
}
