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
      allow {}
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
      allow {}
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
      none {}
    }

    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesAmazonIpReputationList"

        rule_action_override {
          name = "AWSManagedIPReputationList"
          action_to_use {
            block {}
          }
        }

        rule_action_override {
          name = "AWSManagedReconnaissanceList"
          action_to_use {
            block {}
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
      none {}
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
      none {}
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
    name     = "AWS-AWSManagedRulesBotControlRuleSet"
    priority = 5

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesBotControlRuleSet"
      }
    }

    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "AWS-AWSManagedRulesBotControlRuleSet"
    }
  }

  rule {
    name     = "AWS-AWSManagedRulesAnonymousIpList"
    priority = 6

    override_action {
      none {}
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

  # Issue a javascript-based challenge to any remaining requests
  rule {
    name     = "gitlab-challenge"
    priority = 7

    action {
      challenge {}
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
