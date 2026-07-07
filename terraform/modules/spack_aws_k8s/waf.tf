resource "aws_wafv2_ip_set" "vpc_nat_ips" {
  name               = "vpc-nat-ips${local.suffix}"
  scope              = "REGIONAL"
  ip_address_version = "IPV4"
  addresses          = [for ip in module.vpc.nat_public_ips : "${ip}/32"]
}

resource "aws_wafv2_ip_set" "allowed_ips" {
  name               = "allowed-ips${local.suffix}"
  scope              = "REGIONAL"
  ip_address_version = "IPV4"
  addresses = [
    "128.223.202.0/24", # UO's IP block
    "66.194.253.20/32"  # Kitware's VPN
  ]
}

resource "aws_wafv2_web_acl" "gateway" {
  name        = "spack-gateway-waf${local.suffix}"
  scope       = "REGIONAL"
  description = "WAF protection for the spack Gateway ALB"

  default_action {
    allow {}
  }

  # Allow requests originating from inside the cluster VPC
  rule {
    name     = "AllowVpcNatIps"
    priority = 0

    action {
      count {}
    }

    statement {
      ip_set_reference_statement {
        arn = aws_wafv2_ip_set.vpc_nat_ips.arn
      }
    }

    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "AllowVpcNatIps"
    }
  }

  # Allow requests from trusted IP ranges
  rule {
    name     = "AllowTrustedIps"
    priority = 1

    action {
      count {}
    }

    statement {
      ip_set_reference_statement {
        arn = aws_wafv2_ip_set.allowed_ips.arn
      }
    }

    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "AllowTrustedIps"
    }
  }

  rule {
    name     = "AWS-AWSManagedRulesAmazonIpReputationList"
    priority = 2

    override_action {
      count {}
    }

    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesAmazonIpReputationList"

        rule_action_override {
          name = "AWSManagedIPReputationList"
          action_to_use {
            count {}
          }
        }

        rule_action_override {
          name = "AWSManagedReconnaissanceList"
          action_to_use {
            count {}
          }
        }

        rule_action_override {
          name = "AWSManagedIPDDoSList"
          action_to_use {
            count {}
          }
        }
      }
    }

    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "AWS-AWSManagedRulesAmazonIpReputationList"
    }
  }

  rule {
    name     = "AWS-AWSManagedRulesCommonRuleSet"
    priority = 3

    override_action {
      count {}
    }

    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesCommonRuleSet"
      }
    }

    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "AWS-AWSManagedRulesCommonRuleSet"
    }
  }

  rule {
    name     = "AWS-AWSManagedRulesKnownBadInputsRuleSet"
    priority = 4

    override_action {
      count {}
    }

    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
      }
    }

    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "AWS-AWSManagedRulesKnownBadInputsRuleSet"
    }
  }

  rule {
    name     = "AWS-AWSManagedRulesAnonymousIpList"
    priority = 5

    override_action {
      count {}
    }

    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesAnonymousIpList"
      }
    }

    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "AWS-AWSManagedRulesAnonymousIpList"
    }
  }

  # BotControl is a paid rule group (charged per request inspected). It runs last among the
  # managed rule groups so that cheaper rules (IP reputation, common, anonymous IP) can block
  # requests before they reach it. The scope-down statement further excludes health-check and
  # static asset requests that don't need bot inspection.
  rule {
    name     = "AWS-AWSManagedRulesBotControlRuleSet"
    priority = 6

    override_action {
      count {}
    }

    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesBotControlRuleSet"

        managed_rule_group_configs {
          aws_managed_rules_bot_control_rule_set {
            inspection_level = "COMMON"
          }
        }
      }
    }

    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "AWS-AWSManagedRulesBotControlRuleSet"
    }
  }

  # Issue a javascript-based challenge to any remaining requests
  rule {
    name     = "gitlab-challenge"
    priority = 7

    action {
      count {}
    }

    statement {
      byte_match_statement {
        search_string = "gitlab.${local.domain_suffix}spack.io"
        field_to_match {
          single_header {
            name = "host"
          }
        }
        text_transformation {
          priority = 0
          type     = "NONE"
        }
        positional_constraint = "EXACTLY"
      }
    }

    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "gitlab-challenge"
    }
  }

  visibility_config {
    sampled_requests_enabled   = true
    cloudwatch_metrics_enabled = true
    metric_name                = "spack-gateway-waf${local.suffix}"
  }
}

resource "aws_wafv2_web_acl_association" "gateway" {
  resource_arn = data.aws_lb.gateway.arn
  web_acl_arn  = aws_wafv2_web_acl.gateway.arn
}

resource "aws_cloudwatch_log_group" "gateway_waf" {
  # WAF requires log group names to start with "aws-waf-logs-"
  name              = "aws-waf-logs-spack-gateway${local.suffix}"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_resource_policy" "gateway_waf" {
  policy_name = "aws-waf-logs-spack-gateway${local.suffix}"
  policy_document = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "delivery.logs.amazonaws.com"
        }
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.gateway_waf.arn}:*"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }
    ]
  })
}

resource "aws_wafv2_web_acl_logging_configuration" "gateway" {
  resource_arn            = aws_wafv2_web_acl.gateway.arn
  log_destination_configs = [aws_cloudwatch_log_group.gateway_waf.arn]
}
