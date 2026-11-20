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

  # Block requests with this specific user agent string
  rule {
    name     = "BlockBotNet"
    priority = 2

    action {
      block {}
    }

    statement {
      and_statement {
        # Matches the botnet's fixed browser fingerprint...
        statement {
          byte_match_statement {
            search_string = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            field_to_match {
              single_header {
                name = "user-agent"
              }
            }
            text_transformation {
              priority = 0
              type     = "NONE"
            }
            positional_constraint = "EXACTLY"
          }
        }
        # ...but real Chrome always sends Sec-CH-UA; requiring it to be absent
        # keeps this rule from matching a real browser that happens to share
        # this (aging) UA string.
        statement {
          not_statement {
            statement {
              size_constraint_statement {
                field_to_match {
                  single_header {
                    name = "sec-ch-ua"
                  }
                }
                text_transformation {
                  priority = 0
                  type     = "NONE"
                }
                comparison_operator = "GE"
                size                = 0
              }
            }
          }
        }
      }
    }

    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "BlockBotNet"
    }
  }

  rule {
    name     = "AWS-AWSManagedRulesAmazonIpReputationList"
    priority = 3

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
    priority = 4

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
    priority = 5

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
    priority = 6

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

  # Challenge GETs of expensive repository HTML pages, which crawlers hammer
  rule {
    name     = "gitlab-challenge"
    priority = 8

    action {
      challenge {}
    }

    # Default 5 min token expiry breaks in-page XHRs on these paths
    challenge_config {
      immunity_time_property {
        immunity_time = 3600
      }
    }

    statement {
      and_statement {
        # STARTS_WITH also matches "host:443" and a trailing-dot host
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
              type     = "LOWERCASE"
            }
            positional_constraint = "STARTS_WITH"
          }
        }
        # Exempt trusted sources here so this rule is safe whatever the Allow* rules do
        statement {
          not_statement {
            statement {
              or_statement {
                statement {
                  ip_set_reference_statement {
                    arn = aws_wafv2_ip_set.vpc_nat_ips.arn
                  }
                }
                statement {
                  ip_set_reference_statement {
                    arn = aws_wafv2_ip_set.allowed_ips.arn
                  }
                }
              }
            }
          }
        }
        # Challenges only work on GET requests
        statement {
          byte_match_statement {
            search_string = "GET"
            field_to_match {
              method {}
            }
            text_transformation {
              priority = 0
              type     = "NONE"
            }
            positional_constraint = "EXACTLY"
          }
        }
        # HTML pages only: raw and archive downloads go to curl and scripts,
        # which would silently save the 202 challenge page
        statement {
          regex_match_statement {
            regex_string = "/-/(commits?|compare|blob|tree|blame|network|graphs)(/|$)"
            field_to_match {
              uri_path {}
            }
            text_transformation {
              priority = 0
              type     = "URL_DECODE"
            }
          }
        }
        # Same for .patch/.diff downloads and .atom feeds under those paths
        statement {
          not_statement {
            statement {
              regex_match_statement {
                regex_string = "\\.(patch|diff|atom)$"
                field_to_match {
                  uri_path {}
                }
                text_transformation {
                  priority = 0
                  type     = "URL_DECODE"
                }
              }
            }
          }
        }
        # Same for ?raw= and ?inline= downloads of blobs
        statement {
          not_statement {
            statement {
              regex_match_statement {
                regex_string = "(^|&)(raw|inline)="
                field_to_match {
                  query_string {}
                }
                text_transformation {
                  priority = 0
                  type     = "LOWERCASE"
                }
              }
            }
          }
        }
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
