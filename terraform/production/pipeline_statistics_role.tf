resource "aws_iam_role" "put_object_in_pipeline_statistics" {
  name        = "PutObjectInPipelineStatistics"
  description = "Managed by Terraform. Grant access to write to the pipeline-statistics folder of the spack-logs bucket."
  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Principal" : {
          "Federated" : module.production_cluster.oidc_provider_arn
        },
        "Action" : "sts:AssumeRoleWithWebIdentity",
        "Condition" : {
          "StringEquals" : {
            "${module.production_cluster.oidc_provider}:aud" : "sts.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_iam_policy" "put_object_in_pipeline_statistics" {
  name        = "PutObjectInPipelineStatistics"
  description = "Managed by Terraform. Grant ability to write logs to pipeline-statistics prefix of spack-logs bucket"
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : "s3:PutObject",
        "Resource" : "arn:aws:s3:::spack-logs/pipeline-statistics/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "put_object_in_pipeline_statistics" {
  role       = aws_iam_role.put_object_in_pipeline_statistics.name
  policy_arn = aws_iam_policy.put_object_in_pipeline_statistics.arn
}

# The ServiceAccount to be used by the gitlab pipeline stats job
resource "kubectl_manifest" "gitlab_api_scrape_service_account" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      name: gitlab-api-scrape
      namespace: custom
      annotations:
        # PutObjectInPipelineStatistics
        eks.amazonaws.com/role-arn: ${aws_iam_role.put_object_in_pipeline_statistics.arn}
  YAML
  depends_on = [
    aws_iam_role_policy_attachment.put_object_in_pipeline_statistics
  ]
}
