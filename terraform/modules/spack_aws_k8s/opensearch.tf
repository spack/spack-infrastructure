locals {
  domain_endpoint_name        = "opensearch.${var.deployment_name == "prod" ? "" : "${var.deployment_name}."}spack.io"
  cognito_enabled             = var.deployment_name == "prod"
  opensearch_master_user_name = "admin"
}

resource "random_password" "opensearch_password" {
  length  = 64
  special = true
}

resource "aws_opensearch_domain" "spack" {
  domain_name = "spack${var.deployment_name == "prod" ? "" : "-${var.deployment_name}"}"

  engine_version = "OpenSearch_1.3"

  advanced_security_options {
    enabled                        = true
    internal_user_database_enabled = true

    dynamic "master_user_options" {
      for_each = var.deployment_name == "prod" ? [] : [1]

      content {
        master_user_name     = local.opensearch_master_user_name
        master_user_password = random_password.opensearch_password.result
      }
    }
  }

  auto_tune_options {
    desired_state       = var.deployment_name == "prod" ? "ENABLED" : "DISABLED"
    rollback_on_disable = "NO_ROLLBACK"
  }

  cluster_config {
    instance_count = 2
    instance_type  = var.opensearch_instance_type
    zone_awareness_config {
      availability_zone_count = 2
    }

    zone_awareness_enabled = true
  }

  # TODO: our AWS Cognito config for OpenSearch is not encoded in Terraform yet.
  # We want the existing Cognito set up for our production OpenSearch cluster to
  # remain in use, so we use a dynamic block to ensure it's ignored for non-production
  # OpenSearch deployments.
  dynamic "cognito_options" {
    for_each = local.cognito_enabled ? [1] : []

    content {
      enabled          = true
      identity_pool_id = "us-east-1:ff2664d7-a403-42ba-8407-5d90b3eaa948" # TODO: encode this into terraform
      role_arn         = aws_iam_role.opensearch_cognito_role.arn
      user_pool_id     = "us-east-1_k6YnDTVBT" # TODO: encode this into terraform
    }
  }

  domain_endpoint_options {
    custom_endpoint_enabled         = true
    custom_endpoint                 = local.domain_endpoint_name
    custom_endpoint_certificate_arn = aws_acm_certificate.opensearch.arn
    enforce_https                   = true
    tls_security_policy             = "Policy-Min-TLS-1-0-2019-07"
  }

  ebs_options {
    ebs_enabled = true
    iops        = 3000
    volume_size = var.opensearch_volume_size
    volume_type = "gp3"
  }

  encrypt_at_rest {
    enabled = true
  }

  log_publishing_options {
    # TODO: encode cloudwatch in terraform
    cloudwatch_log_group_arn = "arn:aws:logs:us-east-1:588562868276:log-group:/aws/OpenSearchService/domains/spack/application-logs"
    enabled                  = var.deployment_name == "prod" ? true : false
    log_type                 = "ES_APPLICATION_LOGS"
  }

  node_to_node_encryption {
    enabled = true
  }

  snapshot_options {
    automated_snapshot_start_hour = 0
  }

  access_policies = data.aws_iam_policy_document.main.json

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [
    aws_acm_certificate_validation.opensearch
  ]
}

data "aws_iam_policy_document" "main" {
  statement {
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    actions   = ["es:ESHttp*"]
    resources = ["arn:aws:es:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:domain/${"spack${var.deployment_name == "prod" ? "" : "-${var.deployment_name}"}"}/*"]
  }
}


# Configure custom domain name
resource "aws_acm_certificate" "opensearch" {
  domain_name       = local.domain_endpoint_name
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

resource "aws_route53_record" "opensearch" {
  name    = local.domain_endpoint_name
  records = [aws_opensearch_domain.spack.endpoint]
  ttl     = 300
  type    = "CNAME"
  zone_id = data.aws_route53_zone.spack_io.zone_id
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

resource "kubectl_manifest" "opensearch_secrets" {
  yaml_body = <<-YAML
     apiVersion: v1
     kind: Secret
     metadata:
       name: opensearch-secrets
       namespace: custom
     data:
       opensearch-endpoint: ${base64encode("https://${aws_opensearch_domain.spack.endpoint}")}
       opensearch-username: ${base64encode("${local.opensearch_master_user_name}")}
       opensearch-password: ${base64encode("${random_password.opensearch_password.result}")}
   YAML
}
