variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "ai-code-review-sandbox"
}

variable "microvm_image_name" {
  description = "Name of the pre-built Lambda MicroVM image"
  type        = string
  default     = "code-review-sandbox"
}

variable "bedrock_model_id" {
  description = "Bedrock model for AI analysis"
  type        = string
  default     = "moonshotai.kimi-k2.5"
}
