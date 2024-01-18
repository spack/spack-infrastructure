resource "aws_s3_bucket" "bootstrap" {
  bucket = "spack-bootstrap${local.suffix}"
}

resource "aws_s3_bucket_public_access_block" "bootstrap" {
  bucket = aws_s3_bucket.bootstrap.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "bootstrap" {
  bucket = aws_s3_bucket.bootstrap.id

  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Sid" : "PublicRead",
        "Effect" : "Allow",
        "Principal" : "*",
        "Action" : "s3:GetObject",
        "Resource" : "arn:aws:s3:::${aws_s3_bucket.bootstrap.bucket}/*"
      },
      {
        "Sid" : "StephenSachsPclusterWrite",
        "Effect" : "Allow",
        "Principal" : {
          "AWS" : "arn:aws:iam::679174810898:root"
        },
        "Action" : [
          "s3:GetObject*",
          "s3:PutObject*",
          "s3:DeleteObject*"
        ],
        "Resource" : "arn:aws:s3:::${aws_s3_bucket.bootstrap.bucket}/pcluster/*"
      }
    ]
  })
}
