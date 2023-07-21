resource "aws_s3_bucket" "gitlab_object_stores" {
  for_each = toset(["artifacts", "uploads"])

  bucket = "spack-${var.deployment_name}-gitlab-${each.value}"

  lifecycle {
    prevent_destroy = true
  }
}

# Bucket policy that prevents deletion of GitLab buckets.
resource "aws_s3_bucket_policy" "gitlab_object_stores" {
  for_each = aws_s3_bucket.gitlab_object_stores

  bucket = each.value.id

  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Principal" : "*"
        "Effect" : "Deny",
        "Action" : [
          "s3:DeleteBucket",
        ],
        "Resource" : each.value.arn,
      }
    ]
  })
}
