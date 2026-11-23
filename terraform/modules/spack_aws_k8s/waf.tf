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

  # Block anonymous repo page views; a crawler solves challenges at scale
  rule {
    name     = "gitlab-block-repo-browsing"
    priority = 7

    action {
      block {
        custom_response {
          response_code            = 403
          custom_response_body_key = "gitlab-repo-browsing"
        }
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
                # Presence-only cookie check (spoofable); known_sign_in is only set if "Notify on unknown sign-in" is enabled
                statement {
                  regex_match_statement {
                    regex_string = "known_sign_in|remember_user_token"
                    field_to_match {
                      cookies {
                        match_pattern {
                          all {}
                        }
                        match_scope       = "KEY"
                        oversize_handling = "CONTINUE"
                      }
                    }
                    text_transformation {
                      priority = 0
                      type     = "NONE"
                    }
                  }
                }
              }
            }
          }
        }
        # Rails runs the full GET action for HEAD
        statement {
          regex_match_statement {
            regex_string = "^(GET|HEAD)$"
            field_to_match {
              method {}
            }
            text_transformation {
              priority = 0
              type     = "NONE"
            }
          }
        }
        # Repo pages/downloads with or without /-/; "-"-led segments can't precede (skips /-/jobs/)
        statement {
          regex_match_statement {
            # GitLab's refs route serves JSON for any extension (refs.xml, refs.JSON)
            regex_string = "^(/[^/-][^/]*)+/(-/)?((commits?|compare|blob|tree|blame|network|graphs|find_file|files|raw|archive)(/|\\.json$|$)|refs(/|\\.[^/]*$|$))"
            field_to_match {
              uri_path {}
            }
            text_transformation {
              priority = 0
              type     = "URL_DECODE"
            }
            # Rails squeezes repeated slashes, so /-//blob/ must match too
            text_transformation {
              priority = 1
              type     = "NORMALIZE_PATH"
            }
          }
        }
        # Skip the REST API, help docs and git clones, which share these path words
        statement {
          not_statement {
            statement {
              or_statement {
                statement {
                  byte_match_statement {
                    search_string = "/help/"
                    field_to_match {
                      uri_path {}
                    }
                    text_transformation {
                      priority = 0
                      type     = "URL_DECODE"
                    }
                    text_transformation {
                      priority = 1
                      type     = "NORMALIZE_PATH"
                    }
                    positional_constraint = "STARTS_WITH"
                  }
                }
                statement {
                  byte_match_statement {
                    search_string = "/api/"
                    field_to_match {
                      uri_path {}
                    }
                    text_transformation {
                      priority = 0
                      type     = "URL_DECODE"
                    }
                    text_transformation {
                      priority = 1
                      type     = "NORMALIZE_PATH"
                    }
                    positional_constraint = "STARTS_WITH"
                  }
                }
                statement {
                  byte_match_statement {
                    search_string = "/info/refs"
                    field_to_match {
                      uri_path {}
                    }
                    text_transformation {
                      priority = 0
                      type     = "URL_DECODE"
                    }
                    text_transformation {
                      priority = 1
                      type     = "NORMALIZE_PATH"
                    }
                    positional_constraint = "ENDS_WITH"
                  }
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
      metric_name                = "gitlab-block-repo-browsing"
    }
  }

  custom_response_body {
    key          = "gitlab-repo-browsing"
    content_type = "TEXT_PLAIN"
    content      = "Anonymous repository browsing is disabled on this CI mirror. Pipelines and jobs are still available. Sign in to browse code here (if already signed in, sign out and back in), or browse it on the upstream project.\n"
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
