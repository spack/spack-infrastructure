locals {
  s3_bucket_policies = {
    "spack-binaries" = {
      resources = [
        "arn:aws:s3:::spack-binaries/*/armpl-*",
        "arn:aws:s3:::spack-binaries/*/intel-*"
      ]
      allowed = "arn:aws:iam::588562868276:user/protected-binary-mirror"
    }

    "spack-binaries-prs" = {
      resources = [
        "arn:aws:s3:::spack-binaries-prs/*/armpl-*",
        "arn:aws:s3:::spack-binaries-prs/*/intel-*"
      ]
      allowed = "arn:aws:iam::588562868276:user/pull-requests-binary-mirror"
    }
  }
}

resource "aws_s3_bucket_policy" "protected_binaries_restricted" {
  for_each = local.s3_bucket_policies

  bucket = "${each.key}"

  policy = jsonencode({
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "PublicRead",
        "Effect": "Allow",
        "Principal": "*",
        "Action": "s3:GetObject",
        "Resource": "arn:aws:s3:::${each.key}/*"
      }
    ]
  })
}
