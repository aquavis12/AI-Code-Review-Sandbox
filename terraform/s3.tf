# ==================================
# S3 — Results Bucket
# ==================================

resource "aws_s3_bucket" "results" {
  bucket = "${var.project_name}-results-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_lifecycle_configuration" "results_lifecycle" {
  bucket = aws_s3_bucket.results.id

  rule {
    id     = "cleanup-old-reviews"
    status = "Enabled"

    filter {
    }

    expiration {
      days = 30
    }
  }
}

# ==================================
# S3 — Build Artifacts Bucket (for MicroVM image)
# ==================================

resource "aws_s3_bucket" "artifacts" {
  bucket = "${var.project_name}-artifacts-${data.aws_caller_identity.current.account_id}"
}
