data "tls_certificate" "github_actions" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github_actions" {
  count = var.deployment_name == "prod" ? 1 : 0

  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github_actions.certificates.0.sha1_fingerprint]
}

# Allow github actions run from the develop branch of spack/spack to put objects into the source mirror
resource "aws_iam_role" "github_actions_put_to_source_mirror" {
  count = var.deployment_name == "prod" ? 1 : 0

  name = "GitHubLLNLSourceMirror"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "sts:AssumeRoleWithWebIdentity"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github_actions[0].arn
        }
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com",
            "token.actions.githubusercontent.com:sub" = "repo:spack/spack-packages:ref:refs/heads/develop"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "github_actions_put_to_source_mirror" {
  count = var.deployment_name == "prod" ? 1 : 0

  name = "PutToSpackLLNLSourceMirror"
  role = aws_iam_role.github_actions_put_to_source_mirror[0].name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "PutToSpackLLNLSourceMirror"
        Effect   = "Allow"
        Action   = "s3:PutObject"
        Resource = "arn:aws:s3:::spack-llnl-mirror/_source-cache/*"
      },
      {
        Sid      = "ListSpackLLNLSourceMirror"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = "arn:aws:s3:::spack-llnl-mirror"
        Condition = {
          StringLike = {
            "s3:prefix" = ["_source-cache/*"]
          }
        }
      }
    ]
  })
}
