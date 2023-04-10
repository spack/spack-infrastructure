locals {
  endpoint = "opensearch${var.deployment_name == "production" ? "" : ".${var.deployment_name}"}.spack.io"
}

resource "aws_opensearch_domain" "spack" {
  domain_name = "spack${var.deployment_name == "production" ? "" : "-${var.deployment_name}"}"

  engine_version = "OpenSearch_1.3"

  advanced_security_options {
    enabled                        = true
    internal_user_database_enabled = true
  }

  auto_tune_options {
    desired_state       = "ENABLED"
    rollback_on_disable = "NO_ROLLBACK"
  }

  cluster_config {
    instance_count = 2
    instance_type  = "r6g.xlarge.search"
    zone_awareness_config {
      availability_zone_count = 2
    }

    zone_awareness_enabled = true
  }

  cognito_options {
    enabled          = true
    identity_pool_id = "us-east-1:ff2664d7-a403-42ba-8407-5d90b3eaa948" # TODO: encode this into terraform
    role_arn         = aws_iam_role.opensearch_cognito_role.arn
    user_pool_id     = "us-east-1_k6YnDTVBT" # TODO: encode this into terraform
  }

  domain_endpoint_options {
    custom_endpoint_enabled         = true
    custom_endpoint                 = local.endpoint
    custom_endpoint_certificate_arn = aws_acm_certificate.opensearch.arn
    enforce_https                   = true
    tls_security_policy             = "Policy-Min-TLS-1-0-2019-07"
  }

  ebs_options {
    ebs_enabled = true
    iops        = 3000
    volume_size = 500
    volume_type = "gp3"
  }

  encrypt_at_rest {
    enabled = true
    # TODO: encode this KMS resource in terraform
    kms_key_id = "arn:aws:kms:us-east-1:588562868276:key/6385d11c-f377-4778-96a6-5da54416b3cb"
  }

  log_publishing_options {
    # TODO: encode cloudwatch in terraform
    cloudwatch_log_group_arn = "arn:aws:logs:us-east-1:588562868276:log-group:/aws/OpenSearchService/domains/spack/application-logs"
    enabled                  = true
    log_type                 = "ES_APPLICATION_LOGS"
  }

  node_to_node_encryption {
    enabled = true
  }

  snapshot_options {
    automated_snapshot_start_hour = 0
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [
    aws_acm_certificate_validation.opensearch
  ]
}

# Configure custom domain name
resource "aws_acm_certificate" "opensearch" {
  domain_name       = local.endpoint
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "opensearch_validation" {
  for_each = {
    for dvo in aws_acm_certificate.opensearch.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = false
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.aws_route53_zone.spack_io.zone_id
}

resource "aws_acm_certificate_validation" "opensearch" {
  certificate_arn         = aws_acm_certificate.opensearch.arn
  validation_record_fqdns = [for record in aws_route53_record.opensearch_validation : record.fqdn]
}

# Configure role needed for OpenSearch to interact with Cognito
data "aws_iam_policy" "amazon_opensearch_service_cognito_access" {
  arn = "arn:aws:iam::aws:policy/AmazonOpenSearchServiceCognitoAccess"
}

resource "aws_iam_role" "opensearch_cognito_role" {
  name        = "OpenSearchCognitoAccessRole-${var.deployment_name}"
  description = "IAM role that gives OpenSearch permissions to configure the Amazon Cognito user and identity pools and use them for authentication."
  assume_role_policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Effect" : "Allow",
        "Principal" : {
          "Service" : "opensearchservice.amazonaws.com"
        },
        "Action" : "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "opensearch_congito_role_policy_attach" {
  role       = aws_iam_role.opensearch_cognito_role.name
  policy_arn = data.aws_iam_policy.amazon_opensearch_service_cognito_access.arn
}

# Configure role needed for fluent-bit to post data to OpenSearch
resource "aws_iam_role" "fluent_bit_role" {
  name        = "FluentBitRole-${var.deployment_name}"
  description = "IAM role that, when associated with a k8s service account, allows a fluent-bit pod to post logs to OpenSearch."

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
            "${module.eks.oidc_provider}:sub" : "system:serviceaccount:fluent-bit:fluent-bit",
            "${module.eks.oidc_provider}:aud" : "sts.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "fluent_bit_policy" {
  name = "FluentBitPolicy-${var.deployment_name}"
  role = aws_iam_role.fluent_bit_role.id
  policy = jsonencode({
    "Version" : "2012-10-17",
    "Statement" : [
      {
        "Action" : [
          "es:ESHttp*"
        ],
        "Resource" : aws_opensearch_domain.spack.arn,
        "Effect" : "Allow"
      }
    ]
  })
}
