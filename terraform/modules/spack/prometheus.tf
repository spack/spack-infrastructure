resource "aws_s3_bucket" "metrics_bucket" {
  bucket = "spack-${var.deployment_name}-prometheus-thanos-metrics"

  lifecycle {
    prevent_destroy = true
  }
}

# Bucket policy that prevents deletion bucket.
resource "aws_s3_bucket_policy" "metrics_bucket" {
  bucket = aws_s3_bucket.metrics_bucket.id

  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Principal" : "*"
        "Effect" : "Deny",
        "Action" : [
          "s3:DeleteBucket",
        ],
        "Resource" : aws_s3_bucket.metrics_bucket.arn,
      }
    ]
  })
}

resource "aws_iam_policy" "metrics_bucket" {
  name        = "PrometheusThanosPolicy-${var.deployment_name}"
  description = "Managed by Terraform. Grants required permissions for Thanos to read/write to the Prometheus metrics bucket."

  # https://docs.gitlab.com/ee/install/aws/manual_install_aws.html#create-an-iam-policy
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Action" : [
          "s3:ListBucket",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:PutObject",
        ],
        "Resource" : [
          aws_s3_bucket.metrics_bucket.arn,
          "${aws_s3_bucket.metrics_bucket.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role" "metrics_bucket" {
  name        = "PrometheusThanosRole-${var.deployment_name}"
  description = "Managed by Terraform. Role for Thanos to assume so that it can access the Prometheus metrics bucket."
  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Principal" : {
          "Federated" : module.eks.oidc_provider_arn
        },
        "Action" : "sts:AssumeRoleWithWebIdentity",
        "Condition" : {
          "StringEquals" : {
            "${module.eks.oidc_provider}:aud" : "sts.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "metrics_bucket" {
  role       = aws_iam_role.metrics_bucket.name
  policy_arn = aws_iam_policy.metrics_bucket.arn
}

resource "kubectl_manifest" "prometheus_thanos_secret" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: Secret
    metadata:
      name: thanos-objstore
      namespace: monitoring
    stringData:
      objstore.yaml: |
        type: S3
        config:
          endpoint: "s3.${data.aws_region.current.name}.amazonaws.com"
          bucket: "${aws_s3_bucket.metrics_bucket.id}"
          insecure: false
          signature_version2: false
          trace:
            enable: true

  YAML
}


resource "kubectl_manifest" "prometheus_thanos_config_map" {
  yaml_body = <<-YAML
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: prometheus-thanos-config
      namespace: monitoring
    data:
      values.yaml: |
        prometheus:
          serviceAccount:
            create: true
            name: "prometheus-thanos-sa"
            annotations:
              eks.amazonaws.com/role-arn: ${aws_iam_role.metrics_bucket.arn}
          prometheusSpec:
            thanos:
              objectStorageConfig:
                name: ${kubectl_manifest.prometheus_thanos_secret.name}
                key: objstore.yaml
  YAML
}
